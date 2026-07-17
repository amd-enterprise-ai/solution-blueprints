// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// OpenTelemetry-shaped envelope helpers — INFERENCE plane.
//
// Same intent as the connector's otel.js: keep SQLite the audit source of truth
// and ADD OTEL-shaped fields inside the event JSON so O11y/Tokenomics views can
// consume it as OTLP. The inference plane additionally carries GenAI semantic-
// convention span attributes (gen_ai.*) so the llm.request event maps cleanly to
// an OTEL GenAI "chat" span.
//
// GenAI semconv reference: https://opentelemetry.io/docs/specs/semconv/gen-ai/

import { randomUUID } from "node:crypto";

export const SCHEMA_VERSION = "1.0";
export const INGEST_SOURCE = "lemonade-proxy";
export const SERVICE_NAME = "lemonade-proxy";

export function newEventId() {
  return randomUUID();
}

export function resourceBlock(identity) {
  return {
    "service.name": SERVICE_NAME,
    "service.namespace": identity.tenant,
    "service.instance.id": identity.deviceId,
    "telemetry.sdk.name": "axis-telemetry",
    "telemetry.sdk.language": "nodejs",
  };
}

export function otelEnvelope({ identity, trace, spanId, parentSpanId }) {
  return {
    event_id: newEventId(),
    schema_version: SCHEMA_VERSION,
    ingest_source: INGEST_SOURCE,
    trace_id: trace?.trace_id ?? null,
    span_id: spanId ?? null,
    parent_span_id: parentSpanId ?? null,
    resource: resourceBlock(identity),
  };
}

/** GenAI semantic-convention span attributes for an llm.request.
 *  - provider: "lemonade" (local) or "frontier" (escalated cloud gateway).
 *  - execution_location: "deskside" (local APU) or "cloud" (frontier) — the
 *    Tokenomics signal, alongside cost_basis.
 *  Token/model fields are null-safe (the backend may omit usage). */
export function genAiAttributes({
  requestedModel,
  servedModel,
  provider,
  executionLocation,
  inputTokens,
  outputTokens,
  stopReason,
}) {
  return {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": provider ?? null,
    "gen_ai.request.model": requestedModel ?? null,
    "gen_ai.response.model": servedModel ?? null,
    "gen_ai.usage.input_tokens": inputTokens ?? null,
    "gen_ai.usage.output_tokens": outputTokens ?? null,
    "gen_ai.response.finish_reasons": stopReason ? [stopReason] : null,
    "execution_location": executionLocation ?? null,
  };
}
