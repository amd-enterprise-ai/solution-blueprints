// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Audit event builders for the TOOL plane, plus the shared SQLite sink.
//
// The sink itself lives in stack/shared/sqlite_sink.js (shared with the
// inference plane, WAL + busy_timeout + fail-soft). This module re-exports it as
// SqliteEventSink and provides the tool-plane event builders.
//
// Event schema (stable):
//   axis.session_start  { event, time, identity{session,user,tenant,device_id},
//                         policy{id, source} }
//   axis.toolcall       { event, time, identity, policy,
//                         command{seq, argv_redacted},
//                         decision, result{exit, duration_ms, timed_out} }
//   axis.session_end    { event, time, identity }
//
// AXIS is the sole tool-plane enforcement layer (Landlock + seccomp + netns);
// there is no separate admission gate in this deployment.
//
// Privacy note: only the REDACTED argv is persisted. AXIS performs no command-
// string inspection, so a command carrying an inline secret runs — but the audit
// record never stores the raw argv, so the audit DB does not become a secret
// sink. redactCommand() (axis.js) masks known secret shapes before persistence.

import { SqliteSink } from "../../shared/sqlite_sink.js";
import { otelEnvelope } from "./otel.js";
import { newSpanId } from "./trace.js";

// Re-export the shared sink under the tool-plane name.
export { SqliteSink as SqliteEventSink };

function nowEpoch() {
  return Date.now() / 1000;
}

function policyBlock(identity) {
  return { id: identity.policyId, source: identity.policySource };
}

/** session_start — emitted once per session. */
export function buildSessionStart(identity) {
  return {
    event: "axis.session_start",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: null, spanId: null, parentSpanId: null }),
    identity: identity.identityBlock(),
    policy: policyBlock(identity),
  };
}

/** session_end — emitted once per session. */
export function buildSessionEnd(identity) {
  return {
    event: "axis.session_end",
    time: nowEpoch(),
    ...otelEnvelope({ identity, trace: null, spanId: null, parentSpanId: null }),
    identity: identity.identityBlock(),
  };
}

/** toolcall — one per tool call, carrying identity, policy provenance, the
 *  REDACTED command, the decision, and the AXIS sandbox result.
 *
 *  decision values:
 *    allow   — AXIS ran the command to a clean exit (exit == 0)
 *    error   — AXIS ran the command but it exited non-zero (command failure OR a
 *              Landlock/seccomp denial — the connector cannot distinguish the two
 *              from the exit code alone, so this is NOT labelled "deny")
 *    block   — execution refused before AXIS ran (reserved; audit sink down)
 *    unknown — no exit observed
 *
 *  Only `argv_redacted` is persisted — never the raw argv (see module header). */
export function buildToolCall({
  identity,
  seq,
  argvRedacted,
  decision,
  result,
  trace,
}) {
  const spanId = newSpanId();
  return {
    event: "axis.toolcall",
    time: nowEpoch(),
    ...otelEnvelope({
      identity,
      trace,
      spanId,
      parentSpanId: trace?.root_span_id ?? null,
    }),
    attributes: {
      "axis.turn": trace?.turn ?? null,
      "tool.name": "run",
    },
    identity: identity.identityBlock(),
    policy: policyBlock(identity),
    command: {
      seq,
      argv_redacted: argvRedacted,
    },
    decision,
    result: result
      ? {
          exit: result.code,
          duration_ms: result.durationMs,
          timed_out: Boolean(result.timedOut),
        }
      : { exit: null, duration_ms: null, timed_out: false },
  };
}
