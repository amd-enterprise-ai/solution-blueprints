// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// SQLite event sink + builder functions for the INFERENCE plane.
//
// Writes all audit events synchronously to a local SQLite database using
// better-sqlite3.
//
// Privacy: we record METADATA ONLY — model, timing, token counts, and
// prompt/completion CHAR COUNTS. The raw prompt and completion text are never
// stored. This plane has no guardrail integration. Rows go directly to SQLite.
//
//   llm.session_start { event, time, identity, policy{id,source} }
//   llm.request       { event, time, identity, policy, request{...}, decision,
//                       result{...}, routing{...}, gpu }
//   llm.session_end   { event, time, identity }
//
// Schema:
//   events (id INTEGER PRIMARY KEY AUTOINCREMENT,
//            time REAL,
//            event TEXT,
//            session TEXT,
//            data TEXT)

import { SqliteSink } from "../../shared/sqlite_sink.js";
import { otelEnvelope, genAiAttributes } from "./otel.js";
import { newSpanId, newTraceId } from "./trace.js";

// Re-export the shared sink under the inference-plane name. The shared sink is
// fail-soft (a bad AUDIT_DB path degrades to a no-op instead of crashing the
// proxy) and opens in WAL mode so it coexists with the tool plane's writer.
export { SqliteSink as SqliteLlmEventSink };

function nowEpoch() {
  return Date.now() / 1000;
}

function policyBlock(identity) {
  return { id: identity.policyId, source: identity.policySource };
}

/** The vLLM Semantic Router decision, shaped for the audit record. `upstream`
 *  is the base URL the proxy actually forwarded to. */
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

// Session lifecycle events carry a SESSION-SCOPED trace (not a per-turn trace):
// per-turn traces cover the request/toolcall events, but session_start/end
// bracket the whole session, so they share one session trace_id, each get their
// own span_id, and have no parent (root). Per TELEMETRY_CONTRACT §8, every event
// must carry non-null trace_id/span_id. The caller passes a shared session trace
// so start/end correlate; if omitted we mint one so the fields are never null.
export function buildLlmSessionStart(identity, trace) {
  const sessionTrace = trace ?? { trace_id: newTraceId() };
  return {
    event: "llm.session_start",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: sessionTrace, spanId: newSpanId(), parentSpanId: null }),
    identity: identity.identityBlock(),
    policy: policyBlock(identity),
  };
}

export function buildLlmSessionEnd(identity, trace) {
  const sessionTrace = trace ?? { trace_id: newTraceId() };
  return {
    event: "llm.session_end",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: sessionTrace, spanId: newSpanId(), parentSpanId: null }),
    identity: identity.identityBlock(),
  };
}

/** One event per LLM call through the proxy.
 *  `decision` is the proxy's final disposition:
 *    allow   — forwarded and completed (upstream status < 400)
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
  trace,
  gpu,
}) {
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
  };
}
