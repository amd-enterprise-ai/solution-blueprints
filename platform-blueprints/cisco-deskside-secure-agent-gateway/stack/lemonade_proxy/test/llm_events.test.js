// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { userInfo } from "node:os";

import { ProxyIdentity, resolveUser } from "../src/identity.js";
import {
  LlmEventSink,
  buildLlmSessionStart,
  buildLlmSessionEnd,
  buildLlmRequest,
  contentBlock,
} from "../src/llm_events.js";

function id() {
  return new ProxyIdentity({
    LLM_SESSION: "cc-sess",
    LLM_USER: "amd",
    LLM_TENANT: "client-deskside",
    LLM_DEVICE_ID: "node-1",
  });
}

test("identity honors LLM_SESSION and falls back to AXIS_SESSION for correlation", () => {
  assert.equal(new ProxyIdentity({ LLM_SESSION: "a" }).session, "a");
  assert.equal(new ProxyIdentity({ AXIS_SESSION: "b" }).session, "b");
  assert.match(new ProxyIdentity({}).session, /^lp-/);
});

test("resolveUser: LLM_USER || AXIS_USER as source=env, else OS user as source=os", () => {
  assert.deepEqual(resolveUser({ LLM_USER: "carol" }), { user: "carol", source: "env" });
  assert.deepEqual(resolveUser({ AXIS_USER: "dave" }), { user: "dave", source: "env" });
  assert.deepEqual(resolveUser({}), { user: userInfo().username, source: "os" });
});

test("identity block carries user + user_source, matching the tool plane shape", () => {
  const blk = new ProxyIdentity({ LLM_USER: "amd" }).identityBlock();
  assert.equal(blk.user, "amd");
  assert.equal(blk.user_source, "env");
  assert.ok("session" in blk && "tenant" in blk && "device_id" in blk);
});

test("session_start carries identity + inference policy provenance", () => {
  const e = buildLlmSessionStart(id());
  assert.equal(e.event, "llm.session_start");
  assert.equal(e.identity.session, "cc-sess");
  assert.equal(e.policy.id, "inference-proxy");
  assert.equal(e.policy.source, "local-control");
});

test("session_end carries identity", () => {
  const e = buildLlmSessionEnd(id());
  assert.equal(e.event, "llm.session_end");
  assert.equal(e.identity.session, "cc-sess");
});

test("llm.request carries request/result/decision + both defenseclaw verdicts", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "Qwen3-8B-GGUF",
    endpoint: "/v1/messages",
    stream: true,
    messages: 2,
    promptChars: 42,
    decision: "allow",
    result: {
      status: 200,
      durationMs: 1234,
      promptTokens: 11,
      completionTokens: 7,
      completionChars: 30,
      stopReason: "end_turn",
    },
    defenseclawRequest: { decision: "allow", severity: "NONE", findings: [], wouldBlock: false, reachable: true },
    defenseclawResponse: { decision: "allow", severity: "LOW", findings: ["PII"], wouldBlock: true, reachable: true },
  });
  assert.equal(e.event, "llm.request");
  assert.equal(e.request.seq, 0);
  assert.equal(e.request.model, "Qwen3-8B-GGUF");
  assert.equal(e.request.stream, true);
  assert.equal(e.request.prompt_chars, 42);
  assert.equal(e.decision, "allow");
  assert.equal(e.result.status, 200);
  assert.equal(e.result.prompt_tokens, 11);
  assert.equal(e.result.completion_tokens, 7);
  assert.equal(e.defenseclaw_request.action, "allow");
  assert.equal(e.defenseclaw_response.severity, "LOW");
  assert.deepEqual(e.defenseclaw_response.findings, ["PII"]);
});

test("llm.request carries OTEL envelope + GenAI attributes + trace/gpu", () => {
  const trace = { trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 2 };
  const gpu = { busy_percent: 90, power_w: 25, energy_joules: 42 };
  const e = buildLlmRequest({
    identity: id(),
    seq: 3,
    model: "Qwen3-8B-GGUF",
    requestedModel: "claude-sonnet-5",
    endpoint: "/v1/messages",
    stream: true,
    messages: 1,
    promptChars: 10,
    decision: "allow",
    result: { status: 200, durationMs: 100, promptTokens: 5, completionTokens: 9, completionChars: 20, stopReason: "end_turn" },
    routing: { enabled: true, reachable: true, tier: "local", selectedModel: null, decision: null, complexity: null, upstream: "http://x", classifyMs: 1 },
    defenseclawRequest: null,
    defenseclawResponse: null,
    trace,
    gpu,
  });
  // OTEL envelope
  assert.match(e.event_id, /^[0-9a-f-]{36}$/);
  assert.equal(e.schema_version, "1.0");
  assert.equal(e.ingest_source, "lemonade-proxy");
  assert.equal(e.trace_id, "a".repeat(32));
  assert.match(e.span_id, /^[0-9a-f]{16}$/);
  assert.equal(e.parent_span_id, "b".repeat(16));
  assert.equal(e.resource["service.name"], "lemonade-proxy");
  assert.equal(e.resource["service.instance.id"], "node-1");
  // GenAI semconv attributes
  assert.equal(e.attributes["gen_ai.operation.name"], "chat");
  assert.equal(e.attributes["gen_ai.provider.name"], "lemonade");
  assert.equal(e.attributes["gen_ai.request.model"], "claude-sonnet-5");
  assert.equal(e.attributes["gen_ai.response.model"], "Qwen3-8B-GGUF");
  assert.equal(e.attributes["gen_ai.usage.input_tokens"], 5);
  assert.equal(e.attributes["gen_ai.usage.output_tokens"], 9);
  assert.deepEqual(e.attributes["gen_ai.response.finish_reasons"], ["end_turn"]);
  assert.equal(e.attributes["execution_location"], "deskside");
  assert.equal(e.attributes["axis.turn"], 2);
  // GPU block
  assert.deepEqual(e.gpu, gpu);
});

test("frontier tier maps to provider=frontier / execution_location=cloud, gpu null", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "claude-opus-4.8",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 5,
    decision: "allow",
    result: { status: 200, durationMs: 10, promptTokens: 1, completionTokens: 2, completionChars: 3, stopReason: "end_turn" },
    routing: { enabled: true, reachable: true, tier: "frontier", selectedModel: "claude-opus-4.8" },
    defenseclawRequest: null,
    defenseclawResponse: null,
    trace: { trace_id: "c".repeat(32), root_span_id: "d".repeat(16), turn: 0 },
    gpu: null,
  });
  assert.equal(e.attributes["gen_ai.provider.name"], "frontier");
  assert.equal(e.attributes["execution_location"], "cloud");
  assert.equal(e.gpu, null);
});

test("llm.request with no result/verdicts has null fields", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 1,
    model: "m",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 3,
    decision: "unknown",
    result: null,
    defenseclawRequest: null,
    defenseclawResponse: null,
  });
  assert.equal(e.result.status, null);
  assert.equal(e.defenseclaw_request, null);
  assert.equal(e.defenseclaw_response, null);
});

test("content is null by default (privacy: metadata-only build)", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "m",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 3,
    decision: "allow",
    result: null,
    defenseclawRequest: null,
    defenseclawResponse: null,
  });
  assert.equal(e.content, null);
});

test("contentBlock returns null unless capture is enabled", () => {
  assert.equal(
    contentBlock({ capture: false, maxChars: 100, promptText: "hi", completionText: "yo" }),
    null,
  );
});

test("contentBlock returns null when enabled but prompt is empty (no useful content to record)", () => {
  // Only prompt absence causes null — an empty completion alone is still useful
  // on the block path where there is no completion yet.
  assert.equal(
    contentBlock({ capture: true, maxChars: 100, promptText: "" }),
    null,
  );
  assert.equal(
    contentBlock({ capture: true, maxChars: 100, promptText: "", completionText: "" }),
    null,
  );
});

test("contentBlock captures prompt-only (block/502 path: no completion yet)", () => {
  // On the DefenseClaw-block path the completion is absent. The block should
  // still be emitted so the blocked prompt text lands in the audit event.
  const b = contentBlock({ capture: true, maxChars: 100, promptText: "bad request" });
  assert.ok(b, "block emitted even without completion");
  assert.equal(b.prompt, "bad request");
  assert.equal(b.completion, "");
  assert.equal(b.completion_chars, 0);
  assert.equal(b.completion_truncated, false);
});

test("contentBlock captures prompt + completion with original char counts", () => {
  const b = contentBlock({
    capture: true,
    maxChars: 100,
    promptText: "what is 2+2?",
    completionText: "4",
  });
  assert.equal(b.captured, true);
  assert.equal(b.max_chars, 100);
  assert.equal(b.prompt, "what is 2+2?");
  assert.equal(b.prompt_chars, 12);
  assert.equal(b.prompt_truncated, false);
  assert.equal(b.completion, "4");
  assert.equal(b.completion_chars, 1);
  assert.equal(b.completion_truncated, false);
});

test("contentBlock truncates each side to max_chars but reports the true length", () => {
  const b = contentBlock({
    capture: true,
    maxChars: 5,
    promptText: "abcdefghij", // 10 chars
    completionText: "xyz",
  });
  assert.equal(b.prompt, "abcde");
  assert.equal(b.prompt_chars, 10);
  assert.equal(b.prompt_truncated, true);
  assert.equal(b.completion, "xyz");
  assert.equal(b.completion_chars, 3);
  assert.equal(b.completion_truncated, false);
});

test("buildLlmRequest carries a content block when one is supplied", () => {
  const content = contentBlock({
    capture: true,
    maxChars: 8192,
    promptText: "prompt text",
    completionText: "answer text",
  });
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "m",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 11,
    decision: "allow",
    result: { status: 200, durationMs: 1, promptTokens: 1, completionTokens: 1, completionChars: 11, stopReason: "end_turn" },
    defenseclawRequest: null,
    defenseclawResponse: null,
    content,
  });
  assert.equal(e.content.prompt, "prompt text");
  assert.equal(e.content.completion, "answer text");
  assert.equal(e.content.captured, true);
});

test("sink appends JSONL and posts HEC envelope with axis:llm sourcetype", async () => {
  const dir = await mkdtemp(join(tmpdir(), "llmsink-"));
  const path = join(dir, "events.jsonl");
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts });
    return { ok: true, status: 200, text: async () => "{}" };
  };
  try {
    const sink = new LlmEventSink({ sinkPath: path, hecUrl: "http://127.0.0.1:8088", hecToken: "tok", fetchImpl });
    await sink.emit(buildLlmSessionStart(id()));
    const lines = (await readFile(path, "utf8")).trim().split("\n");
    assert.equal(lines.length, 1);
    assert.equal(JSON.parse(lines[0]).event, "llm.session_start");
    assert.match(calls[0].url, /\/services\/collector\/event$/);
    assert.equal(calls[0].opts.headers.Authorization, "Splunk tok");
    const env = JSON.parse(calls[0].opts.body);
    assert.equal(env.sourcetype, "axis:llm");
    assert.equal(env.index, "axis");
    assert.equal(env.event.event, "llm.session_start");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("sink HEC failure never throws", async () => {
  const fetchImpl = async () => {
    throw new Error("down");
  };
  const sink = new LlmEventSink({ hecUrl: "http://127.0.0.1:1", fetchImpl });
  await sink.emit(buildLlmSessionEnd(id()));
});
