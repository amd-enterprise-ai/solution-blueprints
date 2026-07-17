#!/usr/bin/env node
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Lemonade telemetry proxy — the client-side INFERENCE-plane audit choke point.
//
// A transparent HTTP reverse proxy in front of the local Lemonade server. The
// agent host (Claude Code / gaia) points its ANTHROPIC_BASE_URL / LEMONADE_BASE_URL
// at this proxy instead of directly at Lemonade. Every request is forwarded
// byte-for-byte to the upstream; the proxy never alters the data path. On the
// side it:
//   1. identity    — emit llm.session_start once; assign a per-request seq.
//   2. forward     — proxy method/path/headers/body to Lemonade, streaming the
//                    response back to the client while tee-ing it for parsing.
//   3. audit       — build an llm.request event (identity + model + timing +
//                    token counts) -> written to a local SQLite DB.
// On shutdown emit llm.session_end.
//
// Only message-generating endpoints (/v1/messages, /v1/chat/completions) produce
// events; health/model-list/etc. are forwarded silently.

import http from "node:http";

import { ProxyIdentity } from "./identity.js";
import { SemanticRouterClient } from "./router.js";
import { TraceState } from "./trace.js";
import { sampleGpu, gpuBlock } from "./gpu.js";
import {
  SqliteLlmEventSink,
  buildLlmSessionStart,
  buildLlmSessionEnd,
  buildLlmRequest,
} from "./sqlite_events.js";
import { extractRequest, extractResponseJson, parseAnthropicSSE, isNewUserTurn } from "./anthropic.js";
import { anthropicToOpenAI, openAIToAnthropic, openAISSEtoAnthropic } from "./translate.js";

const cfg = {
  port: Number(process.env.LEMON_PROXY_PORT || 13399),
  upstream: (process.env.LEMON_UPSTREAM || "http://127.0.0.1:13305").replace(/\/+$/, ""),
  auditDb: process.env.AUDIT_DB || "./audit.db",
  // Privacy: the inference plane records METADATA ONLY (model, timing, token +
  // char counts, routing). It never stores raw prompt or completion text.
  // vLLM Semantic Router: consult the classify API per prompt, escalate hard
  // prompts to the frontier tier. Off by default (proxy stays a pure passthrough).
  routerEnabled: process.env.LEMON_ROUTER === "on",
  routerUrl: process.env.SEMANTIC_ROUTER_URL || "http://127.0.0.1:8088",
  // Bypass the router and send EVERY call to the frontier tier (the A/B
  // "frontier-only" baseline arm). Off by default. Opt-in: LEMON_FORCE_FRONTIER=1.
  forceFrontier: process.env.LEMON_FORCE_FRONTIER === "1",
  // Which text the router classifies: "full" (whole flattened prompt — default,
  // preserves the original behavior) or "last_user" (just the final user turn,
  // the task actually being asked). Classifying the full ~35KB agent harness
  // drowns the difficulty signal; last_user is what anthropic.js documents as the
  // intended classify input. Opt-in via LEMON_ROUTER_CLASSIFY_INPUT=last_user.
  routerClassifyInput: process.env.LEMON_ROUTER_CLASSIFY_INPUT === "last_user" ? "last_user" : "full",
  // Router classify timeout override (ms, 0 => library default 5s). CPU-only
  // nodes need longer because the embedding classify shares cores with local
  // inference. Set via ROUTER_CLASSIFY_TIMEOUT_MS.
  routerClassifyTimeoutMs: Number(process.env.ROUTER_CLASSIFY_TIMEOUT_MS || 0) || undefined,
  // Translate the LOCAL tier between the Anthropic Messages API and the OpenAI
  // Chat Completions API (off by default). Needed where the local Lemonade build
  // serves only OpenAI (CPU llama.cpp). The frontier tier is never translated.
  // Opt-in via LEMON_TRANSLATE_LOCAL=1.
  translateLocal: process.env.LEMON_TRANSLATE_LOCAL === "1",
  lemonadeOpenAIPath: process.env.LEMONADE_OPENAI_PATH || "/api/v1/chat/completions",
  localModel: process.env.LEMON_MODEL || "Qwen3-Coder-30B-A3B-Instruct-GGUF",
  // Frontier tier (configurable): default = AMD LLM Gateway (Anthropic-compatible,
  // like Lemonade). For Anthropic direct set FRONTIER_UPSTREAM=https://api.anthropic.com,
  // FRONTIER_AUTH_HEADER=x-api-key, FRONTIER_MODEL=claude-haiku-4-5-20251001.
  frontierUpstream: (process.env.FRONTIER_UPSTREAM || "https://<llm-gateway>/Anthropic").replace(/\/+$/, ""),
  frontierModel: process.env.FRONTIER_MODEL || "claude-opus-4.8",
  frontierAuthHeader: process.env.FRONTIER_AUTH_HEADER || "Ocp-Apim-Subscription-Key",
  frontierAuthKey: process.env.FRONTIER_AUTH_KEY || process.env.GATEWAY_KEY || "",
  // Extra static headers for the frontier (e.g. anthropic-version for Anthropic
  // direct), as JSON: FRONTIER_EXTRA_HEADERS='{"anthropic-version":"2023-06-01"}'.
  frontierExtraHeaders: parseJsonEnv(process.env.FRONTIER_EXTRA_HEADERS),
};

function parseJsonEnv(v) {
  if (!v) return {};
  try {
    const o = JSON.parse(v);
    return o && typeof o === "object" ? o : {};
  } catch {
    return {};
  }
}

const identity = new ProxyIdentity(process.env);
// This plane is the trace authority: it sees the user prompt, so it detects a new
// turn, mints a trace, and writes it to the shared statefile the tool plane reads.
const traceState = new TraceState(identity.session, process.env);
const router = new SemanticRouterClient({
  enabled: cfg.routerEnabled,
  apiUrl: cfg.routerUrl,
  frontierModel: cfg.frontierModel,
  timeoutMs: cfg.routerClassifyTimeoutMs,
});
// Frontier escalation is only possible when a frontier auth key is configured;
// without it, a "frontier" decision still routes local (fail-safe) but is
// recorded so the operator can see the missing credential.
const frontierReady = Boolean(cfg.frontierAuthKey);
const sink = new SqliteLlmEventSink({ dbPath: cfg.auditDb });

const MESSAGE_PATHS = ["/v1/messages", "/v1/chat/completions"];
const isMessageEndpoint = (url) => MESSAGE_PATHS.some((p) => url.split("?")[0].endsWith(p));

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

// Headers we must not forward verbatim (framing/host are recomputed downstream).
const STRIP_REQ = new Set(["host", "content-length", "accept-encoding", "connection"]);
const STRIP_RES = new Set(["content-length", "content-encoding", "transfer-encoding", "connection"]);

function forwardReqHeaders(req) {
  const h = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (!STRIP_REQ.has(k.toLowerCase())) h[k] = v;
  }
  // Force an unencoded response so we can parse SSE/JSON as it streams.
  h["accept-encoding"] = "identity";
  return h;
}

async function ensureStarted() {
  if (identity.start()) {
    sink.emit(buildLlmSessionStart(identity));
  }
}

async function handle(req, res) {
  const bodyBuf = await readBody(req).catch(() => Buffer.alloc(0));
  const url = req.url || "/";
  const audited = req.method === "POST" && isMessageEndpoint(url);

  if (!audited) {
    await proxyPassthrough(req, res, url, bodyBuf);
    return;
  }

  await ensureStarted();
  const seq = identity.nextSeq();
  const started = Date.now();
  const endpoint = url.split("?")[0];

  let reqInfo = { model: "unknown", stream: false, messages: 0, promptText: "" };
  let reqBody = null;
  try {
    reqBody = JSON.parse(bodyBuf.toString("utf8") || "{}");
    reqInfo = extractRequest(reqBody);
  } catch {
    /* non-JSON body: forward anyway, telemetry stays coarse */
  }

  // Turn detection: a genuinely new user prompt (not a tool_result continuation)
  // starts a new trace; otherwise this call belongs to the current turn's trace.
  const trace = reqBody && isNewUserTurn(reqBody) ? traceState.startTurn() : traceState.ensure();

  // Routing decision (vLLM Semantic Router, consult-only). Escalate to the
  // frontier tier only when the router says so AND a frontier key exists;
  // otherwise the request stays on local Lemonade (byte-for-byte).
  // LEMON_FORCE_FRONTIER=1 bypasses the router entirely and sends every call
  // to the frontier tier (used by the "frontier-only" baseline arm).
  let routed;
  if (cfg.forceFrontier) {
    routed = { enabled: false, reachable: false, tier: "frontier", decision: "forced-frontier", complexity: null, selectedModel: cfg.frontierModel, classifyMs: null };
  } else {
    const classifyText = cfg.routerClassifyInput === "last_user" ? reqInfo.lastUserText : reqInfo.promptText;
    routed = await router.route(classifyText);
  }
  const escalate = routed.tier === "frontier" && frontierReady;
  const upstreamBase = escalate ? cfg.frontierUpstream : cfg.upstream;
  routed.upstream = upstreamBase;
  // When we can't honor a frontier decision (no key), record that we served local.
  if (routed.tier === "frontier" && !frontierReady) routed.tier = "local";

  // GPU consumption is only meaningful for LOCAL inference (the frontier tier runs
  // in the cloud). Sample the APU before forwarding; sample again after completion
  // and combine into a per-request gpu block with an energy estimate.
  const gpuStart = escalate ? null : sampleGpu();

  const fwdHeaders = forwardReqHeaders(req);
  let fwdBody = bodyBuf.length ? bodyBuf : undefined;
  if (escalate) {
    // Only on escalation do we touch the body: swap the model to the frontier id
    // and attach the frontier auth header(s).
    fwdHeaders[cfg.frontierAuthHeader] = cfg.frontierAuthKey;
    for (const [k, v] of Object.entries(cfg.frontierExtraHeaders)) fwdHeaders[k] = v;
    try {
      const obj = JSON.parse(bodyBuf.toString("utf8") || "{}");
      obj.model = cfg.frontierModel;
      fwdBody = Buffer.from(JSON.stringify(obj));
    } catch {
      /* non-JSON body: forward as-is (telemetry stays coarse) */
    }
  }

  // LOCAL-tier Anthropic->OpenAI translation (opt-in, LEMON_TRANSLATE_LOCAL=1).
  // Only when NOT escalating: rewrite the Anthropic body to an OpenAI Chat
  // Completions body aimed at the OpenAI path; the response is translated back
  // below. Frontier calls stay Anthropic byte-for-byte (translate=false).
  const translate = cfg.translateLocal && !escalate;
  let targetUrl = `${upstreamBase}${url}`;
  if (translate) {
    targetUrl = `${upstreamBase}${cfg.lemonadeOpenAIPath}`;
    fwdHeaders["content-type"] = "application/json";
    if (reqBody) {
      try {
        fwdBody = Buffer.from(JSON.stringify(anthropicToOpenAI(reqBody, cfg.localModel)));
      } catch {
        /* fall back to the original body */
      }
    }
  }

  // Surface the routing decision on the client response (additive headers; body
  // is never altered). These mirror a semantic router's x-vsr-* headers.
  const routeHeaders = {
    "x-lemon-router": routed.enabled ? "on" : "off",
    "x-lemon-tier": routed.tier || "local",
  };
  if (routed.selectedModel) routeHeaders["x-lemon-selected-model"] = routed.selectedModel;
  if (routed.complexity) routeHeaders["x-lemon-complexity"] = routed.complexity;

  // Forward to the chosen upstream, streaming the response while accumulating.
  let upstream;
  try {
    upstream = await fetch(targetUrl, {
      method: req.method,
      headers: fwdHeaders,
      body: fwdBody,
    });
  } catch (err) {
    const durationMs = Date.now() - started;
    sink.emit(
      buildLlmRequest({
        identity,
        seq,
        model: escalate ? cfg.frontierModel : reqInfo.model,
        requestedModel: reqInfo.model,
        endpoint,
        stream: reqInfo.stream,
        messages: reqInfo.messages,
        promptChars: reqInfo.promptText.length,
        decision: "unknown",
        result: { status: 502, durationMs },
        routing: routed,
        trace,
        gpu: gpuBlock(gpuStart, escalate ? null : sampleGpu(), durationMs),
      }),
    );
    res.writeHead(502, { ...routeHeaders, "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "api_error", message: String(err) } }));
    return;
  }

  const resHeaders = { ...routeHeaders };
  upstream.headers.forEach((v, k) => {
    if (!STRIP_RES.has(k.toLowerCase())) resHeaders[k] = v;
  });

  const upstreamIsSSE = (upstream.headers.get("content-type") || "").includes("event-stream");
  let raw;
  let parsed = { completionText: "", promptTokens: null, completionTokens: null, stopReason: null };

  if (translate && upstream.ok) {
    // Collect the OpenAI response fully, translate it back to the Anthropic shape
    // the client expects, then send the translated body. (Buffered by design —
    // Lemonade is the latency bottleneck, not this step.)
    const oaiRaw = await upstream.text().catch(() => "");
    let clientBody;
    if (upstreamIsSSE) {
      clientBody = openAISSEtoAnthropic(oaiRaw, reqInfo.model);
      resHeaders["content-type"] = "text/event-stream";
      parsed = parseAnthropicSSE(clientBody);
    } else {
      let oai = {};
      try {
        oai = JSON.parse(oaiRaw || "{}");
      } catch {
        /* best-effort */
      }
      const anth = openAIToAnthropic(oai, reqInfo.model);
      clientBody = JSON.stringify(anth);
      resHeaders["content-type"] = "application/json";
      parsed = extractResponseJson(anth);
    }
    res.writeHead(upstream.status, resHeaders);
    res.write(clientBody);
    res.end();
    raw = clientBody;
  } else {
    res.writeHead(upstream.status, resHeaders);
    raw = await streamAndCollect(upstream, res);
    // Parse completion + usage from what we streamed.
    try {
      parsed = upstreamIsSSE ? parseAnthropicSSE(raw) : extractResponseJson(JSON.parse(raw || "{}"));
    } catch {
      /* best-effort */
    }
  }

  const durationMs = Date.now() - started;
  const decision = upstream.status < 400 ? "allow" : "unknown";
  // Second GPU sample (local tier only) -> per-request gpu block with energy est.
  const gpu = gpuBlock(gpuStart, escalate ? null : sampleGpu(), durationMs);

  // Emit the audit event. The recorded model is the frontier id when escalated.
  sink.emit(
    buildLlmRequest({
      identity,
      seq,
      model: escalate ? cfg.frontierModel : reqInfo.model,
      requestedModel: reqInfo.model,
      endpoint: url.split("?")[0],
      stream: reqInfo.stream,
      messages: reqInfo.messages,
      promptChars: reqInfo.promptText.length,
      decision,
      result: {
        status: upstream.status,
        durationMs,
        promptTokens: parsed.promptTokens,
        completionTokens: parsed.completionTokens,
        completionChars: parsed.completionText.length,
        stopReason: parsed.stopReason,
      },
      routing: routed,
      trace,
      gpu,
    }),
  );
}

/** Stream an upstream fetch Response body to the client response, returning the
 *  full body as a string for telemetry parsing. */
async function streamAndCollect(upstream, res) {
  const chunks = [];
  if (!upstream.body) {
    const txt = await upstream.text().catch(() => "");
    if (txt) res.write(txt);
    res.end();
    return txt;
  }
  const reader = upstream.body.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const buf = Buffer.from(value);
      chunks.push(buf);
      res.write(buf);
    }
  } catch {
    /* client/upstream hangup: end with what we have */
  }
  res.end();
  return Buffer.concat(chunks).toString("utf8");
}

/** Transparent pass-through for non-audited paths (health, models, …). */
async function proxyPassthrough(req, res, url, bodyBuf) {
  try {
    const upstream = await fetch(`${cfg.upstream}${url}`, {
      method: req.method,
      headers: forwardReqHeaders(req),
      body: req.method === "GET" || req.method === "HEAD" ? undefined : bodyBuf.length ? bodyBuf : undefined,
    });
    const resHeaders = {};
    upstream.headers.forEach((v, k) => {
      if (!STRIP_RES.has(k.toLowerCase())) resHeaders[k] = v;
    });
    res.writeHead(upstream.status, resHeaders);
    await streamAndCollect(upstream, res);
  } catch (err) {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: String(err) }));
  }
}

const server = http.createServer((req, res) => {
  handle(req, res).catch((err) => {
    if (!res.headersSent) res.writeHead(500, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: String(err) }));
  });
});

async function shutdown() {
  if (identity.end()) {
    sink.emit(buildLlmSessionEnd(identity));
  }
  sink.close();
  server.close(() => process.exit(0));
  // Safety net if close hangs on keep-alive sockets.
  setTimeout(() => process.exit(0), 1000).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// Only auto-listen when run as a program (tests import handle()/builders).
if (process.argv[1] && process.argv[1].endsWith("server.js")) {
  server.listen(cfg.port, "127.0.0.1", () => {
    const bound = server.address().port;
    const routerDesc = cfg.routerEnabled
      ? `on(${cfg.routerUrl} -> frontier ${cfg.frontierModel}@${cfg.frontierUpstream}${frontierReady ? "" : " NO-KEY"})`
      : "off";
    process.stderr.write(
      `[lemonade-proxy] listening on http://127.0.0.1:${bound} -> ${cfg.upstream} ` +
        `(audit_db=${cfg.auditDb}, ` +
        `router=${routerDesc}, force_frontier=${cfg.forceFrontier}, classify=${cfg.routerClassifyInput}, translate_local=${cfg.translateLocal}, ` +
        `session=${identity.session})\n`,
    );
    process.stdout.write(`LEMON_PROXY_URL=http://127.0.0.1:${bound}\n`);
  });
}

export { server, handle, cfg };
