// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Splunk-HEC event builder + local sink for the INFERENCE plane.
//
// Same shipping contract as the connector's splunk_events.js (best-effort HEC
// POST that can never break the request path, plus a local JSONL sink), but a
// distinct sourcetype (axis:llm) into the SAME index (axis) so tool-plane
// (axis.toolcall) and inference-plane (llm.request) events sit side by side and
// correlate by identity.session.
//
// Privacy by default: we ship metadata only — model, timing, token counts,
// prompt/response CHAR COUNTS, and the DefenseClaw verdicts (findings/severity).
// We do NOT ship prompt or completion TEXT by default (mirrors the connector
// shipping exit/duration, not stdout). DefenseClaw sees the content for scanning;
// Splunk sees only the verdict.
//
// Content capture (opt-in): Cisco asked to also land the raw user prompt and the
// LLM answer in the telemetry. This is OFF by default (LLM_CAPTURE_CONTENT=on to
// enable) because it ships potentially sensitive text to the audit index. When
// on, an llm.request additionally carries a `content` block with the prompt and
// completion text, each truncated to LLM_CAPTURE_MAX_CHARS (default 8192) so a
// giant prompt can't bloat the index; the block records whether truncation
// happened so a consumer knows the text is partial.
//
//   llm.session_start { event, time, identity, policy{id,source} }
//   llm.request       { event, time, identity, policy, request{...}, decision,
//                       result{...}, routing{...}, defenseclaw_request{...},
//                       defenseclaw_response{...}, content{...}|null }
//   llm.session_end   { event, time, identity }
//
// The routing block is the vLLM Semantic Router decision (see router.js): which
// tier served the call (local Lemonade vs frontier gateway), the router's
// selected model + complexity signal, and whether the router was reachable. It
// is null on a plain passthrough build (router disabled and never consulted).

import { appendFile } from "node:fs/promises";

import { otelEnvelope, genAiAttributes } from "./otel.js";
import { newSpanId } from "./trace.js";

const SOURCETYPE = "axis:llm";
const INDEX = "axis";

export class LlmEventSink {
  constructor({ sinkPath, hecUrl, hecToken, fetchImpl } = {}) {
    this.sinkPath = sinkPath || null;
    this.hecUrl = hecUrl ? hecUrl.replace(/\/+$/, "") : null;
    this.hecToken = hecToken || "fake-token";
    this.fetch = fetchImpl || globalThis.fetch;
  }

  async emit(event) {
    if (this.sinkPath) {
      await appendFile(this.sinkPath, JSON.stringify(event) + "\n");
    }
    if (this.hecUrl) {
      await this.#postHec(event).catch(() => {});
    }
    return event;
  }

  async #postHec(event) {
    const envelope = { time: event.time, sourcetype: SOURCETYPE, index: INDEX, event };
    await this.fetch(`${this.hecUrl}/services/collector/event`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        Authorization: `Splunk ${this.hecToken}`,
      },
      body: JSON.stringify(envelope),
    });
  }
}

function nowEpoch() {
  return Date.now() / 1000;
}

function policyBlock(identity) {
  return { id: identity.policyId, source: identity.policySource };
}

function dcBlock(v) {
  if (!v) return null;
  return {
    action: v.decision,
    severity: v.severity,
    findings: v.findings,
    would_block: v.wouldBlock,
    reachable: v.reachable,
  };
}

/** Truncate to a char cap, reporting whether anything was dropped. */
function clip(text, maxChars) {
  const s = typeof text === "string" ? text : "";
  if (s.length <= maxChars) return { text: s, truncated: false };
  return { text: s.slice(0, maxChars), truncated: true };
}

/** Opt-in prompt/completion text capture (Cisco ask). `null` unless capture is
 *  enabled AND at least one side has text — so a plain metadata build (the
 *  privacy default) keeps emitting `content: null`. Each side is truncated to
 *  `maxChars`; `*_chars` records the ORIGINAL length so the char counts stay
 *  meaningful even when `*_truncated` is true. */
export function contentBlock({ capture, maxChars, promptText, completionText = "" }) {
  if (!capture) return null;
  const prompt = typeof promptText === "string" ? promptText : "";
  const completion = typeof completionText === "string" ? completionText : "";
  // Emit the block whenever at least the prompt is present — the block path
  // has no completion yet, but the prompt is exactly what was blocked and is
  // the most valuable field in a security audit event.
  if (!prompt) return null;
  // Fix: Number("0") is falsy so || would silently revert to 8192. Use an
  // explicit > 0 guard so LLM_CAPTURE_MAX_CHARS=0 is honoured as "truncate
  // everything" (empty strings, truncated=true when original length > 0).
  const cap = Number.isFinite(maxChars) && maxChars > 0 ? maxChars : 8192;
  const p = clip(prompt, cap);
  const c = clip(completion, cap);
  return {
    captured: true,
    max_chars: cap,
    prompt: p.text,
    prompt_chars: prompt.length,
    prompt_truncated: p.truncated,
    completion: c.text,
    completion_chars: completion.length,
    completion_truncated: c.truncated,
  };
}

/** The vLLM Semantic Router decision, shaped for Splunk. `upstream` is the base
 *  URL the proxy actually forwarded to (local Lemonade or the frontier gateway). */
function routingBlock(r) {
  if (!r) return null;
  return {
    enabled: Boolean(r.enabled),
    reachable: Boolean(r.reachable),
    decision: r.decision ?? null,
    complexity: r.complexity ?? null,
    selected_model: r.selectedModel ?? null,
    tier: r.tier ?? null,
    upstream: r.upstream ?? null,
    classify_ms: r.classifyMs ?? null,
  };
}

export function buildLlmSessionStart(identity) {
  return {
    event: "llm.session_start",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: null, spanId: null, parentSpanId: null }),
    identity: identity.identityBlock(),
    policy: policyBlock(identity),
  };
}

export function buildLlmSessionEnd(identity) {
  return {
    event: "llm.session_end",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: null, spanId: null, parentSpanId: null }),
    identity: identity.identityBlock(),
  };
}

/** One event per LLM call through the proxy.
 *  `decision` is the proxy's final disposition:
 *    allow   — forwarded and completed (upstream status < 400)
 *    block   — DefenseClaw blocked it in action mode (upstream never called)
 *    unknown — upstream error / no status observed */
export function buildLlmRequest({
  identity,
  seq,
  model,
  requestedModel,
  endpoint,
  stream,
  messages,
  promptChars,
  decision,
  result,
  routing,
  defenseclawRequest,
  defenseclawResponse,
  trace,
  gpu,
  content,
}) {
  // Each LLM call is its own span, parented to the turn's root span.
  const spanId = newSpanId();
  const tier = routing?.tier ?? "local";
  const provider = tier === "frontier" ? "frontier" : "lemonade";
  const executionLocation = tier === "frontier" ? "cloud" : "deskside";
  return {
    event: "llm.request",
    time: nowEpoch(),
    ...otelEnvelope({
      identity,
      trace,
      spanId,
      parentSpanId: trace?.root_span_id ?? null,
    }),
    attributes: {
      ...genAiAttributes({
        requestedModel: requestedModel ?? model,
        servedModel: model,
        provider,
        executionLocation,
        inputTokens: result?.promptTokens ?? null,
        outputTokens: result?.completionTokens ?? null,
        stopReason: result?.stopReason ?? null,
      }),
      "axis.turn": trace?.turn ?? null,
    },
    identity: identity.identityBlock(),
    policy: policyBlock(identity),
    request: {
      seq,
      model,
      endpoint,
      stream: Boolean(stream),
      messages: messages ?? null,
      prompt_chars: promptChars ?? null,
    },
    decision,
    routing: routingBlock(routing),
    // GPU consumption for LOCAL inference (null on frontier / when unavailable).
    gpu: gpu ?? null,
    result: result
      ? {
          status: result.status ?? null,
          duration_ms: result.durationMs ?? null,
          prompt_tokens: result.promptTokens ?? null,
          completion_tokens: result.completionTokens ?? null,
          completion_chars: result.completionChars ?? null,
          stop_reason: result.stopReason ?? null,
        }
      : {
          status: null,
          duration_ms: null,
          prompt_tokens: null,
          completion_tokens: null,
          completion_chars: null,
          stop_reason: null,
        },
    defenseclaw_request: dcBlock(defenseclawRequest),
    defenseclaw_response: dcBlock(defenseclawResponse),
    // Opt-in raw prompt/completion text (null on the privacy-default build).
    content: content ?? null,
  };
}
