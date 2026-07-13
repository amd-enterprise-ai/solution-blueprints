// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Splunk-HEC event builder + local sink.
//
// This connector BUILDS the audit events; it does not ship them to a real
// Splunk (another team owns that). Events are written to a local JSONL sink and
// can optionally be POSTed to a local HEC-compatible endpoint (the bundled
// fake_hec.py) so the HEC contract is exercised end to end.
//
// The event schema is stable across both planes, so they land the same shape in
// Splunk:
//   axis.session_start  { event, time, identity{session,user,tenant,device_id},
//                         policy{id, source} }
//   axis.toolcall       { event, time, identity, policy,
//                         command{seq, argv, argv_redacted},
//                         decision, result{exit, duration_ms, timed_out},
//                         defenseclaw{action, severity, findings, would_block} }
//   axis.session_end    { event, time, identity }

import { appendFile } from "node:fs/promises";

import { otelEnvelope } from "./otel.js";
import { newSpanId } from "./trace.js";

const SOURCETYPE = "axis:toolcall";
const INDEX = "axis";

export class SplunkEventSink {
  constructor({ sinkPath, hecUrl, hecToken, fetchImpl, reachableTimeoutMs } = {}) {
    this.sinkPath = sinkPath || null;
    this.hecUrl = hecUrl ? hecUrl.replace(/\/+$/, "") : null;
    this.hecToken = hecToken || "fake-token";
    this.fetch = fetchImpl || globalThis.fetch;
    // Bound the reachable() health probe so a black-holed HEC makes the
    // fail-closed gate refuse quickly instead of hanging on a TCP timeout.
    this.reachableTimeoutMs =
      reachableTimeoutMs ?? (Number(process.env.AUDIT_REACHABLE_TIMEOUT_MS) || 1500);
  }

  /** Append one event to the JSONL sink and optionally POST it to a HEC. The
   *  HEC POST is best-effort: a failure is recorded but never throws, so audit
   *  shipping can't break a tool call. */
  async emit(event) {
    if (this.sinkPath) {
      await appendFile(this.sinkPath, JSON.stringify(event) + "\n");
    }
    if (this.hecUrl) {
      await this.#postHec(event).catch(() => {});
    }
    return event;
  }

  /** Write an event to the durable local JSONL sink only (never the HEC). Used
   *  to record a fail-closed refusal even when the HEC is unreachable. */
  async emitLocal(event) {
    if (this.sinkPath) {
      await appendFile(this.sinkPath, JSON.stringify(event) + "\n");
    }
    return event;
  }

  /** Is the audit sink able to accept events right now? With no HEC configured
   *  the local file sink is always considered reachable. With a HEC, probe its
   *  health endpoint (real Splunk: /services/collector/health, fake_hec:
   *  /health). Returns false on any error so the caller can fail closed. */
  async reachable() {
    if (!this.hecUrl) return true;
    for (const path of ["/services/collector/health", "/health"]) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.reachableTimeoutMs);
      try {
        const res = await this.fetch(`${this.hecUrl}${path}`, {
          method: "GET",
          signal: controller.signal,
        });
        if (res && res.ok) return true;
      } catch {
        /* try next (a timeout aborts and lands here too) */
      } finally {
        clearTimeout(timer);
      }
    }
    return false;
  }

  async #postHec(event) {
    const envelope = {
      time: event.time,
      sourcetype: SOURCETYPE,
      index: INDEX,
      event,
    };
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

/** session_start — emitted once per session. Session-scoped, so trace_id is null
 *  (traces are per-turn, minted by the inference plane). */
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
 *  (redacted) command, the allow/deny/block decision, the AXIS result, and the
 *  DefenseClaw findings. `decision` is the connector's final disposition:
 *    allow  — DefenseClaw allowed and AXIS ran it (exit code is the result)
 *    block  — DefenseClaw blocked it (action mode); AXIS never ran it
 *    deny   — DefenseClaw allowed but AXIS sandbox refused it (exit != 0 from a
 *             landlock/seccomp denial)
 *    unknown — gateway unreachable + fail-open, or no exit observed */
export function buildToolCall({
  identity,
  seq,
  argv,
  argvRedacted,
  decision,
  result,
  defenseclaw,
  trace,
}) {
  // Each tool call is its own span, parented to the turn's root span so a
  // consumer can nest "tool call under the user turn".
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
      argv,
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
    defenseclaw: defenseclaw
      ? {
          action: defenseclaw.decision,
          severity: defenseclaw.severity,
          findings: defenseclaw.findings,
          would_block: defenseclaw.wouldBlock,
          reachable: defenseclaw.reachable,
        }
      : null,
  };
}
