// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Per-turn trace ids (Cisco telemetry delta #3) — INFERENCE-plane authority.
//
// Cisco's trace model: one USER PROMPT plus every LLM call and every tool call
// that happens until the NEXT user prompt is ONE trace. So a single agent session
// (one identity.session) contains MANY trace_ids — one per conversational turn.
//
// The two planes are separate processes, so — exactly like identity.session —
// they can only share a trace_id through an out-of-band seam. The proxy is the
// authority: it is the only component that sees the raw user prompt, so it detects
// a new turn, mints a fresh trace_id + root span, and writes them to a shared
// STATEFILE. The tool-plane connector READS that statefile to stamp its
// axis.toolcall events with the same trace_id (see axis_mcp_connector/src/trace.js).
//
// Statefile path: AXIS_TRACE_STATE (exported by the launcher to BOTH planes, like
// AXIS_SESSION); default ${TMPDIR}/axis-trace-<session>.json. Ids are OpenTelemetry
// format: trace_id = 32 lowercase hex, span_id = 16 lowercase hex.

import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const nowEpoch = () => Date.now() / 1000;

/** 32 lowercase hex chars (16 bytes) — OTEL trace_id. */
export function newTraceId() {
  return randomBytes(16).toString("hex");
}

/** 16 lowercase hex chars (8 bytes) — OTEL span_id. */
export function newSpanId() {
  return randomBytes(8).toString("hex");
}

/** Resolve the shared statefile path for a session. */
export function traceStatePath(session, env = process.env) {
  const override = (env.AXIS_TRACE_STATE || "").trim();
  if (override) return override;
  const safe = String(session || "nosession").replace(/[^A-Za-z0-9._-]/g, "_");
  return join(env.TMPDIR || tmpdir(), `axis-trace-${safe}.json`);
}

/** Shared per-session trace state persisted to a JSON statefile. The proxy owns
 *  writes (it advances the turn); the connector only reads (see readTraceState). */
export class TraceState {
  constructor(session, env = process.env) {
    this.session = session;
    this.path = traceStatePath(session, env);
    this.trace_id = null;
    this.root_span_id = null;
    this.turn = -1;
  }

  /** Begin a new turn: mint a fresh trace + root span, bump the turn counter, and
   *  persist. Returns the new state. Called by the proxy when it sees a genuinely
   *  new user prompt. */
  startTurn() {
    this.trace_id = newTraceId();
    this.root_span_id = newSpanId();
    this.turn += 1;
    this.#persist();
    return this.current();
  }

  /** Ensure a trace exists without advancing the turn (e.g. first call of a
   *  session that wasn't a detectable new-user turn). */
  ensure() {
    if (!this.trace_id) return this.startTurn();
    return this.current();
  }

  current() {
    return { trace_id: this.trace_id, root_span_id: this.root_span_id, turn: this.turn };
  }

  #persist() {
    const payload = {
      session: this.session,
      trace_id: this.trace_id,
      root_span_id: this.root_span_id,
      turn: this.turn,
      updated: nowEpoch(),
    };
    try {
      writeFileSync(this.path, JSON.stringify(payload) + "\n");
    } catch {
      /* best-effort: a statefile write failure must never break inference */
    }
  }
}

/** Read the current trace state written by the proxy. Returns null if the
 *  statefile does not exist yet or can't be parsed. Used by the tool plane. */
export function readTraceState(session, env = process.env) {
  const path = traceStatePath(session, env);
  try {
    const obj = JSON.parse(readFileSync(path, "utf8"));
    if (obj && typeof obj.trace_id === "string") return obj;
  } catch {
    /* no statefile yet / unreadable */
  }
  return null;
}
