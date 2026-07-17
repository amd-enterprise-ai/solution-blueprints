// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// End-to-end: spawn the real proxy in front of a fake Lemonade upstream and a
// fake DefenseClaw, drive a /v1/messages call through it (both JSON and SSE),
// and assert the streamed bytes are faithful AND an llm.request event lands in
// the local sink with the DefenseClaw verdicts attached.

import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SERVER = join(HERE, "..", "src", "server.js");

function listen(server) {
  return new Promise((res) => server.listen(0, "127.0.0.1", () => res(server.address().port)));
}

function startFakeDefenseClaw() {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push({ path: req.url, body });
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ action: "allow", severity: "NONE", findings: [], would_block: false }));
    });
  });
  return { server, seen };
}

function startFakeUpstream(handler) {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push({ path: req.url, body });
      handler(req, res, body);
    });
  });
  return { server, seen };
}

async function waitForPort(port, tries = 100) {
  for (let i = 0; i < tries; i++) {
    const ok = await new Promise((resolve) => {
      const r = http.request({ host: "127.0.0.1", port, path: "/__ping", method: "GET" }, (res) => {
        res.resume();
        resolve(true);
      });
      r.on("error", () => resolve(false));
      r.end();
    });
    if (ok) return;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error("proxy did not come up");
}

function postJson(port, path, obj, headers = {}) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(obj);
    const req = http.request(
      { host: "127.0.0.1", port, path, method: "POST", headers: { "content-type": "application/json", ...headers } },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body }));
      },
    );
    req.on("error", reject);
    req.end(data);
  });
}

async function readEvents(path) {
  const txt = await readFile(path, "utf8").catch(() => "");
  return txt
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));
}

async function withProxy({ upstreamHandler, routerHandler, frontierHandler, extraEnv = {}, run }) {
  const dir = await mkdtemp(join(tmpdir(), "proxy-e2e-"));
  const sinkPath = join(dir, "events.jsonl");
  const dc = startFakeDefenseClaw();
  const up = startFakeUpstream(upstreamHandler);
  const dcPort = await listen(dc.server);
  const upPort = await listen(up.server);

  const env = {
    ...process.env,
    LEMON_PROXY_PORT: "0", // pick below via stdout? simpler: fixed free port
    LEMON_UPSTREAM: `http://127.0.0.1:${upPort}`,
    DEFENSECLAW_URL: `http://127.0.0.1:${dcPort}`,
    SPLUNK_SINK: sinkPath,
    LLM_SESSION: "cc-e2e",
    LLM_USER: "amd",
    // These e2e tests assert byte-for-byte local passthrough + routing; the
    // Anthropic->OpenAI local translation (default on) is exercised by its own
    // suite (translate.test.js). Keep it off here so the passthrough asserts hold.
    LEMON_TRANSLATE_LOCAL: "0",
    ...extraEnv,
  };

  // Optional fake vLLM Semantic Router api (classify endpoint).
  let rt = null;
  if (routerHandler) {
    rt = startFakeUpstream(routerHandler);
    const rtPort = await listen(rt.server);
    env.LEMON_ROUTER = "on";
    env.SEMANTIC_ROUTER_URL = `http://127.0.0.1:${rtPort}`;
  }
  // Optional fake frontier tier (Anthropic-compatible gateway).
  let fr = null;
  if (frontierHandler) {
    fr = startFakeUpstream(frontierHandler);
    const frPort = await listen(fr.server);
    env.FRONTIER_UPSTREAM = `http://127.0.0.1:${frPort}`;
    env.FRONTIER_AUTH_HEADER = env.FRONTIER_AUTH_HEADER || "Ocp-Apim-Subscription-Key";
    env.FRONTIER_AUTH_KEY = env.FRONTIER_AUTH_KEY || "test-frontier-key";
    env.FRONTIER_MODEL = env.FRONTIER_MODEL || "claude-opus-4-8";
  }

  const proxy = spawn("node", [SERVER], { env, stdio: ["ignore", "pipe", "pipe"] });

  // Read the actual listen port from stdout (LEMON_PROXY_URL=...).
  const port = await new Promise((resolve, reject) => {
    let out = "";
    const t = setTimeout(() => reject(new Error("no LEMON_PROXY_URL")), 5000);
    proxy.stdout.on("data", (c) => {
      out += c;
      const m = out.match(/LEMON_PROXY_URL=http:\/\/127\.0\.0\.1:(\d+)/);
      if (m) {
        clearTimeout(t);
        resolve(Number(m[1]));
      }
    });
    proxy.on("exit", () => reject(new Error("proxy exited early")));
  });

  await waitForPort(port);
  try {
    return await run({ port, sinkPath, dc, up, rt, fr, readEvents: () => readEvents(sinkPath) });
  } finally {
    proxy.kill("SIGTERM");
    dc.server.close();
    up.server.close();
    if (rt) rt.server.close();
    if (fr) fr.server.close();
    await rm(dir, { recursive: true, force: true });
  }
}

test("non-streaming: forwards body verbatim and emits llm.request(allow)", async () => {
  const upstreamBody = JSON.stringify({
    content: [{ type: "text", text: "GAIA_AGENT_OK" }],
    usage: { input_tokens: 12, output_tokens: 3 },
    stop_reason: "end_turn",
  });
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(upstreamBody);
    },
    run: async ({ port, readEvents }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "say ok" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, upstreamBody); // faithful passthrough

      // Give the async emit a beat to flush.
      await new Promise((r) => setTimeout(r, 200));
      const events = await readEvents();
      const start = events.find((e) => e.event === "llm.session_start");
      const call = events.find((e) => e.event === "llm.request");
      assert.ok(start, "session_start emitted");
      assert.ok(call, "llm.request emitted");
      assert.equal(call.identity.session, "cc-e2e");
      assert.equal(call.request.model, "Qwen3-8B-GGUF");
      assert.equal(call.request.endpoint, "/v1/messages");
      assert.equal(call.decision, "allow");
      assert.equal(call.result.status, 200);
      assert.equal(call.result.prompt_tokens, 12);
      assert.equal(call.result.completion_tokens, 3);
      assert.equal(call.defenseclaw_request.action, "allow");
      assert.equal(call.defenseclaw_response.action, "allow");
    },
  });
});

test("default build: identity carries user_source and content is null", async () => {
  const upstreamBody = JSON.stringify({
    content: [{ type: "text", text: "OK" }],
    usage: { input_tokens: 4, output_tokens: 1 },
    stop_reason: "end_turn",
  });
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(upstreamBody);
    },
    run: async ({ port, readEvents }) => {
      await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "say ok" }],
      });
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      // LLM_USER=amd is set in withProxy env -> asserted (source=env).
      assert.equal(call.identity.user, "amd");
      assert.equal(call.identity.user_source, "env");
      // Content capture is OFF by default: no prompt/completion text shipped.
      assert.equal(call.content, null);
    },
  });
});

test("LLM_CAPTURE_CONTENT=on: prompt + completion text land in the content block", async () => {
  const upstreamBody = JSON.stringify({
    content: [{ type: "text", text: "the answer is 4" }],
    usage: { input_tokens: 6, output_tokens: 4 },
    stop_reason: "end_turn",
  });
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(upstreamBody);
    },
    extraEnv: { LLM_CAPTURE_CONTENT: "on" },
    run: async ({ port, readEvents }) => {
      await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "what is 2+2?" }],
      });
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.ok(call.content, "content block present when capture on");
      assert.equal(call.content.captured, true);
      assert.equal(call.content.prompt, "what is 2+2?");
      assert.equal(call.content.completion, "the answer is 4");
      assert.equal(call.content.prompt_truncated, false);
      assert.equal(call.content.completion_truncated, false);
    },
  });
});

test("LLM_CAPTURE_CONTENT=on with a small cap truncates but reports true length", async () => {
  const upstreamBody = JSON.stringify({
    content: [{ type: "text", text: "0123456789" }],
    usage: { input_tokens: 6, output_tokens: 4 },
    stop_reason: "end_turn",
  });
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(upstreamBody);
    },
    extraEnv: { LLM_CAPTURE_CONTENT: "on", LLM_CAPTURE_MAX_CHARS: "4" },
    run: async ({ port, readEvents }) => {
      await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "abcdefgh" }],
      });
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.content.max_chars, 4);
      assert.equal(call.content.prompt, "abcd");
      assert.equal(call.content.prompt_chars, 8);
      assert.equal(call.content.prompt_truncated, true);
      assert.equal(call.content.completion, "0123");
      assert.equal(call.content.completion_chars, 10);
      assert.equal(call.content.completion_truncated, true);
    },
  });
});

test("streaming SSE: tees text back and records token usage", async () => {
  const sse = [
    'data: {"type":"message_start","message":{"usage":{"input_tokens":8,"output_tokens":0}}}',
    "",
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello "}}',
    "",
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}',
    "",
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}',
    "",
    "data: [DONE]",
    "",
  ].join("\n");
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.end(sse);
    },
    run: async ({ port, readEvents }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        stream: true,
        messages: [{ role: "user", content: "hi" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, sse); // faithful byte-for-byte SSE passthrough
      await new Promise((r) => setTimeout(r, 200));
      const events = await readEvents();
      const call = events.find((e) => e.event === "llm.request");
      assert.ok(call);
      assert.equal(call.request.stream, true);
      assert.equal(call.result.prompt_tokens, 8);
      assert.equal(call.result.completion_tokens, 5);
      assert.equal(call.result.stop_reason, "end_turn");
      assert.equal(call.result.completion_chars, "Hello world".length);
    },
  });
});

test("non-message path is forwarded without emitting an event", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ status: "ok" }));
    },
    run: async ({ port, readEvents }) => {
      const resp = await new Promise((resolve, reject) => {
        const r = http.request({ host: "127.0.0.1", port, path: "/api/v1/health", method: "GET" }, (res) => {
          let b = "";
          res.on("data", (c) => (b += c));
          res.on("end", () => resolve({ status: res.statusCode, body: b }));
        });
        r.on("error", reject);
        r.end();
      });
      assert.equal(resp.status, 200);
      await new Promise((r) => setTimeout(r, 150));
      const events = await readEvents();
      assert.equal(events.filter((e) => e.event === "llm.request").length, 0);
    },
  });
});

// ---- routing (vLLM Semantic Router) ---------------------------------------

const localBody = JSON.stringify({
  content: [{ type: "text", text: "LOCAL_OK" }],
  usage: { input_tokens: 5, output_tokens: 2 },
  stop_reason: "end_turn",
});
const frontierBody = JSON.stringify({
  content: [{ type: "text", text: "FRONTIER_OK" }],
  usage: { input_tokens: 9, output_tokens: 4 },
  stop_reason: "end_turn",
});

// Count only /v1/messages hits (the waitForPort /__ping GET is also forwarded to
// the local upstream, so raw seen.length would be off by one).
const msgHits = (fake) => fake.seen.filter((s) => s.path.split("?")[0].endsWith("/v1/messages")).length;

function classifyResponder(sel, decision, complexity) {
  return (req, res) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        recommended_model: sel,
        routing_decision: decision,
        matched_signals: { complexity: [complexity] },
      }),
    );
  };
}

test("router-on: simple prompt stays LOCAL (Lemonade), routing block recorded", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    routerHandler: classifyResponder("lemonade-local", "local-simple", "needs_reasoning:easy"),
    frontierHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(frontierBody);
    },
    run: async ({ port, readEvents, fr }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "what is the capital of France?" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, localBody); // served locally, verbatim
      assert.equal(resp.headers["x-lemon-router"], "on");
      assert.equal(resp.headers["x-lemon-tier"], "local");
      assert.equal(resp.headers["x-lemon-selected-model"], "lemonade-local");
      assert.equal(msgHits(fr), 0, "frontier NOT called for a simple prompt");

      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.ok(call.routing);
      assert.equal(call.routing.enabled, true);
      assert.equal(call.routing.reachable, true);
      assert.equal(call.routing.tier, "local");
      assert.equal(call.routing.selected_model, "lemonade-local");
      assert.equal(call.routing.complexity, "needs_reasoning:easy");
    },
  });
});

test("router-on: hard prompt ESCALATES to frontier (model rewritten, auth sent)", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    routerHandler: classifyResponder("claude-opus-4-8", "frontier-reasoning", "needs_reasoning:hard"),
    frontierHandler: (req, res, body) => {
      // assert the proxy rewrote the model + attached the frontier auth header
      const parsed = JSON.parse(body || "{}");
      res.writeHead(200, {
        "content-type": "application/json",
        "x-echo-model": parsed.model || "",
        "x-echo-auth": req.headers["ocp-apim-subscription-key"] || "",
      });
      res.end(frontierBody);
    },
    run: async ({ port, readEvents, up, fr }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "prove sqrt(2) is irrational, every step" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, frontierBody); // served by the frontier
      assert.equal(resp.headers["x-lemon-tier"], "frontier");
      assert.equal(resp.headers["x-lemon-selected-model"], "claude-opus-4-8");
      assert.equal(resp.headers["x-echo-model"], "claude-opus-4-8"); // body model rewritten
      assert.ok(resp.headers["x-echo-auth"]?.length > 0, "auth header injected"); // auth injected
      assert.equal(msgHits(up), 0, "local upstream NOT called when escalated");
      assert.equal(msgHits(fr), 1, "frontier called once");

      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.routing.tier, "frontier");
      assert.equal(call.request.model, "claude-opus-4-8"); // event records the served model
      assert.equal(call.result.prompt_tokens, 9);
      assert.match(call.routing.upstream, /^http:\/\/127\.0\.0\.1:\d+$/);
    },
  });
});

test("router-on but NO frontier key: frontier decision falls back to local", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    routerHandler: classifyResponder("claude-opus-4-8", "frontier-reasoning", "needs_reasoning:hard"),
    extraEnv: { FRONTIER_AUTH_KEY: "", GATEWAY_KEY: "" },
    run: async ({ port, readEvents, up }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "prove sqrt(2) is irrational" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, localBody); // fell back to local
      assert.equal(resp.headers["x-lemon-tier"], "local");
      assert.equal(msgHits(up), 1, "served locally");
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.routing.tier, "local");
      assert.equal(call.routing.selected_model, "claude-opus-4-8"); // router still said frontier
    },
  });
});

test("router down: fail-open, request served locally", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    // point the router at a dead port
    extraEnv: { LEMON_ROUTER: "on", SEMANTIC_ROUTER_URL: "http://127.0.0.1:1" },
    run: async ({ port, readEvents, up }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "anything" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, localBody);
      assert.equal(resp.headers["x-lemon-tier"], "local");
      assert.equal(msgHits(up), 1);
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.routing.enabled, true);
      assert.equal(call.routing.reachable, false); // couldn't reach the router
      assert.equal(call.routing.tier, "local");
    },
  });
});

// ---- opt-in behaviors: force-frontier / last-user classify / local translate --

test("LEMON_FORCE_FRONTIER=1: every call escalates to frontier, router bypassed", async () => {
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    frontierHandler: (req, res, body) => {
      const parsed = JSON.parse(body || "{}");
      res.writeHead(200, {
        "content-type": "application/json",
        "x-echo-model": parsed.model || "",
        "x-echo-auth": req.headers["ocp-apim-subscription-key"] || "",
      });
      res.end(frontierBody);
    },
    extraEnv: { LEMON_FORCE_FRONTIER: "1" },
    run: async ({ port, readEvents, up, fr }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        messages: [{ role: "user", content: "even a trivial turn" }],
      });
      assert.equal(resp.status, 200);
      assert.equal(resp.body, frontierBody); // served by the frontier
      assert.equal(resp.headers["x-lemon-tier"], "frontier");
      assert.equal(resp.headers["x-echo-model"], "claude-opus-4-8");
      assert.ok(resp.headers["x-echo-auth"]?.length > 0, "auth injected");
      assert.equal(msgHits(up), 0, "local upstream NOT called");
      assert.equal(msgHits(fr), 1, "frontier called once");
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.routing.tier, "frontier");
      assert.equal(call.routing.decision, "forced-frontier");
    },
  });
});

test("LEMON_ROUTER_CLASSIFY_INPUT=last_user: router sees only the final user turn", async () => {
  let classifyText = null;
  await withProxy({
    upstreamHandler: (req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(localBody);
    },
    routerHandler: (req, res, body) => {
      try {
        classifyText = JSON.parse(body || "{}").text;
      } catch {
        /* ignore */
      }
      classifyResponder("lemonade-local", "local-simple", "needs_reasoning:easy")(req, res);
    },
    extraEnv: { LEMON_ROUTER_CLASSIFY_INPUT: "last_user" },
    run: async ({ port }) => {
      await postJson(port, "/v1/messages", {
        model: "Qwen3-8B-GGUF",
        system: "HUGE_SYSTEM_HARNESS ".repeat(200),
        messages: [
          { role: "user", content: "FIRST_TURN_should_not_be_classified" },
          { role: "assistant", content: "an intermediate answer" },
          { role: "user", content: "FINAL_TURN_ONLY" },
        ],
      });
      // Only the last user turn is classified — not the system harness or history.
      assert.equal(classifyText, "FINAL_TURN_ONLY");
    },
  });
});

test("LEMON_TRANSLATE_LOCAL=1: Anthropic req -> OpenAI upstream -> Anthropic resp", async () => {
  let upstreamPath = null;
  let upstreamBodyObj = null;
  const oaiResponse = JSON.stringify({
    id: "chatcmpl-1",
    object: "chat.completion",
    choices: [{ index: 0, message: { role: "assistant", content: "TRANSLATED_OK" }, finish_reason: "stop" }],
    usage: { prompt_tokens: 7, completion_tokens: 3 },
  });
  await withProxy({
    upstreamHandler: (req, res, body) => {
      if (req.method === "POST") {
        upstreamPath = req.url;
        try {
          upstreamBodyObj = JSON.parse(body || "{}");
        } catch {
          /* ignore */
        }
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(oaiResponse);
    },
    extraEnv: { LEMON_TRANSLATE_LOCAL: "1", LEMON_MODEL: "Qwen3-Coder-30B" },
    run: async ({ port, readEvents }) => {
      const resp = await postJson(port, "/v1/messages", {
        model: "claude-opus-4-8",
        messages: [{ role: "user", content: "say ok" }],
      });
      assert.equal(resp.status, 200);
      // upstream was hit on the OpenAI path with an OpenAI-shaped body
      assert.equal(upstreamPath, "/api/v1/chat/completions");
      assert.ok(Array.isArray(upstreamBodyObj?.messages), "upstream got OpenAI messages[]");
      assert.equal(upstreamBodyObj.model, "Qwen3-Coder-30B");
      // client received an Anthropic-shaped response translated back from OpenAI
      const anth = JSON.parse(resp.body);
      assert.equal(anth.type, "message");
      assert.equal(anth.role, "assistant");
      assert.deepEqual(anth.content, [{ type: "text", text: "TRANSLATED_OK" }]);
      assert.equal(anth.usage.input_tokens, 7);
      assert.equal(anth.usage.output_tokens, 3);
      await new Promise((r) => setTimeout(r, 200));
      const call = (await readEvents()).find((e) => e.event === "llm.request");
      assert.equal(call.result.prompt_tokens, 7);
      assert.equal(call.result.completion_tokens, 3);
    },
  });
});
