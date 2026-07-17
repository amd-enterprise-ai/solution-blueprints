// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Per-turn trace ids (Cisco telemetry delta #3) — TOOL-plane reader.
//
// The inference-plane proxy is the trace authority: it sees the user prompt,
// detects a new turn, and writes {trace_id, root_span_id, turn} to a shared
// statefile (see lemonade_proxy/src/trace.js). This connector only READS that
// statefile so its axis.toolcall events carry the SAME trace_id as the LLM calls
// in the same turn — that is what lets a Splunk/OTLP consumer reconstruct "one
// user prompt -> its LLM calls -> its tool calls" as a single trace.
//
// If the statefile isn't there yet (a tool call fired before any LLM call, or the
// proxy isn't running), we mint a session-scoped fallback trace so events are
// never trace-less; that fallback is stable for the connector's lifetime.
//
// Ids are OpenTelemetry format: trace_id = 32 hex, span_id = 16 hex.

import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export function newTraceId() {
  return randomBytes(16).toString("hex");
}

export function newSpanId() {
  return randomBytes(8).toString("hex");
}

export function traceStatePath(session, env = process.env) {
  const override = (env.AXIS_TRACE_STATE || "").trim();
  if (override) return override;
  const safe = String(session || "nosession").replace(/[^A-Za-z0-9._-]/g, "_");
  return join(env.TMPDIR || tmpdir(), `axis-trace-${safe}.json`);
}

/** Reads the proxy-written trace statefile; falls back to a stable session-scoped
 *  trace when the proxy hasn't written one. */
export class TraceReader {
  constructor(session, env = process.env) {
    this.session = session;
    this.env = env;
    this.path = traceStatePath(session, env);
    this.fallback = null;
  }

  /** The trace + root span the current tool call belongs to. Prefers the proxy's
   *  live statefile; otherwise a stable per-connector fallback. */
  current() {
    const state = this.#read();
    if (state) return { trace_id: state.trace_id, root_span_id: state.root_span_id, turn: state.turn };
    if (!this.fallback) {
      this.fallback = { trace_id: newTraceId(), root_span_id: newSpanId(), turn: 0 };
    }
    return this.fallback;
  }

  #read() {
    try {
      const obj = JSON.parse(readFileSync(this.path, "utf8"));
      if (obj && typeof obj.trace_id === "string") return obj;
    } catch {
      /* no statefile / unreadable */
    }
    return null;
  }
}
