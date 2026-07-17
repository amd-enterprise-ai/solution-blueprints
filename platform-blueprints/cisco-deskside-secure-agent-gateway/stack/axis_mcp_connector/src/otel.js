// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// OpenTelemetry-shaped envelope helpers (Cisco telemetry delta #2).
//
// Cisco wants the Splunk events consumable as OTLP (trace/span ids, GenAI
// semantic attributes, service identity, schema versioning) — not just as
// SIEM-search audit records. Rather than stand up a separate OTLP exporter, we
// keep HEC as the audit source of truth and ADD OTEL-shaped fields INSIDE the
// existing event JSON. Every field here is additive; the legacy audit fields are
// untouched so existing Splunk searches keep working.
//
// What we add to each event:
//   event_id        unique id per event (OTEL log record / dedup key)
//   schema_version  so both sides can evolve the contract safely
//   ingest_source   which producer emitted it (axis-mcp | lemonade-proxy)
//   trace_id/span_id/parent_span_id   the per-turn trace (see trace.js)
//   resource{...}   OTEL Resource: service.* + telemetry.sdk.*
//   attributes{...} span attributes (GenAI semconv on the inference plane)

import { randomUUID } from "node:crypto";

export const SCHEMA_VERSION = "1.0";
export const INGEST_SOURCE = "axis-mcp";
export const SERVICE_NAME = "axis-mcp-connector";

/** A fresh per-event id. */
export function newEventId() {
  return randomUUID();
}

/** OTEL Resource block: the identity of the service producing the telemetry.
 *  Derived from the session identity so it lines up with the audit identity. */
export function resourceBlock(identity) {
  return {
    "service.name": SERVICE_NAME,
    "service.namespace": identity.tenant,
    "service.instance.id": identity.deviceId,
    "telemetry.sdk.name": "axis-telemetry",
    "telemetry.sdk.language": "nodejs",
  };
}

/** The common OTEL envelope fields added to every event. `trace` may be null for
 *  session-lifecycle events (session scope, not a turn); span ids are then null. */
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
