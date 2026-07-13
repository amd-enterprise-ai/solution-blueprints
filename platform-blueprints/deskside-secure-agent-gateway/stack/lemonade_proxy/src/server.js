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
//   2. defenseclaw — POST the prompt to /api/v1/inspect/request (observe,
//                    fail-open). In action mode a block short-circuits upstream.
//   3. forward     — proxy method/path/headers/body to Lemonade, streaming the
//                    response back to the client while tee-ing it for parsing.
//   4. defenseclaw — POST the completion to /api/v1/inspect/response (observe).
//   5. splunk      — build an llm.request HEC event (identity + model + timing +
//                    token counts + verdicts) -> same index=axis as the tool plane.
// On shutdown emit llm.session_end.
//
// Only message-generating endpoints (/v1/messages, /v1/chat/completions) produce
// events; health/model-list/etc. are forwarded silently.

import http from "node:http";

import { ProxyIdentity } from "./identity.js";
import { DefenseClawInferenceClient } from "./defenseclaw.js";
import { SemanticRouterClient } from "./router.js";
import { TraceState } from "./trace.js";
import { sampleGpu, gpuBlock } from "./gpu.js";
import {
  LlmEventSink,
  buildLlmSessionStart,
  buildLlmSessionEnd,
  buildLlmRequest,
} from "./llm_events.js";
import { extractRequest, extractResponseJson, parseAnthropicSSE, isNewUserTurn } from "./anthropic.js";

const cfg = {
  port: Number(process.env.LEMON_PROXY_PORT || 13399),
  upstream: (process.env.LEMON_UPSTREAM || "http://127.0.0.1:13305").replace(/\/+$/, ""),
  defenseclawUrl: process.env.DEFENSECLAW_URL || "http://127.0.0.1:18970",
  defenseclawToken: process.env.DEFENSECLAW_GATEWAY_TOKEN || "",
  // Inference plane defaults: observe + fail-open (never take inference down).
  defenseclawMode: process.env.DEFENSECLAW_INFERENCE_MODE || "observe",
  defenseclawFailOpen: process.env.DEFENSECLAW_INFERENCE_FAIL_OPEN === "0" ? false : true,
  inspectResponse: process.env.DEFENSECLAW_INSPECT_RESPONSE !== "0",
  splunkSink: process.env.SPLUNK_SINK || null,
  splunkHecUrl: process.env.SPLUNK_HEC_URL || null,
  splunkHecToken: process.env.SPLUNK_HEC_TOKEN || "fake-token",
  // vLLM Semantic Router: consult the classify API per prompt, escalate hard
  // prompts to the frontier tier. Off by default (proxy stays a pure passthrough).
  routerEnabled: process.env.LEMON_ROUTER === "on",
  routerUrl: process.env.SEMANTIC_ROUTER_URL || "http://127.0.0.1:8088",
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
const guard = new DefenseClawInferenceClient({
  baseUrl: cfg.defenseclawUrl,
  token: cfg.defenseclawToken,
  mode: cfg.defenseclawMode,
  failOpen: cfg.defenseclawFailOpen,
});
const router = new SemanticRouterClient({
  enabled: cfg.routerEnabled,
  apiUrl: cfg.routerUrl,
  frontierModel: cfg.frontierModel,
});
// Frontier escalation is only possible when a frontier auth key is configured;
// without it, a "frontier" decision still routes local (fail-safe) but is
// recorded so the operator can see the missing credential.
const frontierReady = Boolean(cfg.frontierAuthKey);
const sink = new LlmEventSink({
  sinkPath: cfg.splunkSink,
  hecUrl: cfg.splunkHecUrl,
  hecToken: cfg.splunkHecToken,
});

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
    await sink.emit(buildLlmSessionStart(identity)).catch(() => {});
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

  // 1. Prompt guardrail (observe/fail-open by default).
  const dcReq = await guard.inspectRequest({
    session: identity.session,
    model: reqInfo.model,
    content: reqInfo.promptText,
  });

  // In action mode a real block short-circuits upstream.
  if (dcReq && dcReq.decision === "block") {
    const durationMs = Date.now() - started;
    await sink
      .emit(
        buildLlmRequest({
          identity,
          seq,
          model: reqInfo.model,
          endpoint: url.split("?")[0],
          stream: reqInfo.stream,
          messages: reqInfo.messages,
          promptChars: reqInfo.promptText.length,
          decision: "block",
          result: { status: 403, durationMs },
          routing: null,
          defenseclawRequest: dcReq,
          defenseclawResponse: null,
          trace,
          gpu: null,
        }),
      )
      .catch(() => {});
    res.writeHead(403, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        type: "error",
        error: { type: "permission_error", message: "blocked by DefenseClaw prompt guardrail" },
      }),
    );
    return;
  }

  // 2. Routing decision (vLLM Semantic Router, consult-only). Escalate to the
  //    frontier tier only when the router says so AND a frontier key exists;
  //    otherwise the request stays on local Lemonade (byte-for-byte).
  const routed = await router.route(reqInfo.promptText);
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

  // Surface the routing decision on the client response (additive headers; body
  // is never altered). These mirror a semantic router's x-vsr-* headers.
  const routeHeaders = {
    "x-lemon-router": routed.enabled ? "on" : "off",
    "x-lemon-tier": routed.tier || "local",
  };
  if (routed.selectedModel) routeHeaders["x-lemon-selected-model"] = routed.selectedModel;
  if (routed.complexity) routeHeaders["x-lemon-complexity"] = routed.complexity;

  // 3. Forward to the chosen upstream, streaming the response while accumulating.
  let upstream;
  try {
    upstream = await fetch(`${upstreamBase}${url}`, {
      method: req.method,
      headers: fwdHeaders,
      body: fwdBody,
    });
  } catch (err) {
    const durationMs = Date.now() - started;
    await sink
      .emit(
        buildLlmRequest({
          identity,
          seq,
          model: escalate ? cfg.frontierModel : reqInfo.model,
          requestedModel: reqInfo.model,
          endpoint: url.split("?")[0],
          stream: reqInfo.stream,
          messages: reqInfo.messages,
          promptChars: reqInfo.promptText.length,
          decision: "unknown",
          result: { status: 502, durationMs },
          routing: routed,
          defenseclawRequest: dcReq,
          defenseclawResponse: null,
          trace,
          gpu: gpuBlock(gpuStart, escalate ? null : sampleGpu(), durationMs),
        }),
      )
      .catch(() => {});
    res.writeHead(502, { ...routeHeaders, "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "api_error", message: String(err) } }));
    return;
  }

  const resHeaders = { ...routeHeaders };
  upstream.headers.forEach((v, k) => {
    if (!STRIP_RES.has(k.toLowerCase())) resHeaders[k] = v;
  });
  res.writeHead(upstream.status, resHeaders);

  const raw = await streamAndCollect(upstream, res);

  // 3. Parse completion + usage from what we streamed.
  const isSSE = (upstream.headers.get("content-type") || "").includes("event-stream");
  let parsed = { completionText: "", promptTokens: null, completionTokens: null, stopReason: null };
  try {
    parsed = isSSE ? parseAnthropicSSE(raw) : extractResponseJson(JSON.parse(raw || "{}"));
  } catch {
    /* best-effort */
  }

  // 4. Completion guardrail (observe).
  let dcRes = null;
  if (cfg.inspectResponse && parsed.completionText) {
    dcRes = await guard.inspectResponse({
      session: identity.session,
      model: reqInfo.model,
      content: parsed.completionText,
    });
  }

  const durationMs = Date.now() - started;
  const decision = upstream.status < 400 ? "allow" : "unknown";
  // Second GPU sample (local tier only) -> per-request gpu block with energy est.
  const gpu = gpuBlock(gpuStart, escalate ? null : sampleGpu(), durationMs);

  // 5. Emit the audit event. The recorded model is the frontier id when escalated.
  await sink
    .emit(
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
        defenseclawRequest: dcReq,
        defenseclawResponse: dcRes,
        trace,
        gpu,
      }),
    )
    .catch(() => {});
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
    await sink.emit(buildLlmSessionEnd(identity)).catch(() => {});
  }
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
        `(defenseclaw=${cfg.defenseclawMode}/${cfg.defenseclawFailOpen ? "fail-open" : "fail-closed"}, ` +
        `router=${routerDesc}, session=${identity.session})\n`,
    );
    process.stdout.write(`LEMON_PROXY_URL=http://127.0.0.1:${bound}\n`);
  });
}

export { server, handle, cfg };
