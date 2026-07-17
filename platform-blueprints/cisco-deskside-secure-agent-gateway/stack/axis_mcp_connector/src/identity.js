// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Agent session identity for the client-side connector.
//
// Each connector process is one agent session. Identity carries who/where the
// agent is (session/user/tenant/device) and a monotonically increasing `seq`
// per tool call, so the audit trail can reconstruct the exact order of actions
// within a session. The lifecycle is session_start (once) -> toolcall (N) ->
// session_end (once).

import { makeSessionId as _makeSessionId, resolveUser as _resolveUser, hostnameSafe } from "../../shared/identity_utils.js";

/** A stable per-process session id. Honors an injected id (e.g. set by a
 *  supervising harness via AXIS_SESSION) so a single logical agent run can be
 *  correlated across restarts; otherwise mints a fresh `cc-<uuid>`. */
export function makeSessionId(envSession) {
  return _makeSessionId(envSession, "cc");
}

/** Resolve the acting user and its provenance for the tool plane.
 *  Env key: AXIS_USER (asserted by launcher); falls back to OS login user. */
export function resolveUser(env = process.env) {
  return _resolveUser(["AXIS_USER"], env);
}

/** Holds the identity of one agent session and hands out tool-call sequence
 *  numbers. Pure/in-memory: emitting the actual lifecycle events is the
 *  splunk_events layer's job, driven by start()/nextSeq()/end() here. */
export class SessionIdentity {
  constructor(env = process.env) {
    this.session = makeSessionId(env.AXIS_SESSION);
    const { user, source } = resolveUser(env);
    this.user = user;
    this.userSource = source;
    this.tenant = (env.AXIS_TENANT || "").trim() || "client-deskside";
    this.deviceId = (env.AXIS_DEVICE_ID || "").trim() || hostnameSafe();
    this.policySource = (env.AXIS_POLICY_SOURCE || "").trim() || "local-control";
    this.policyId = (env.AXIS_POLICY_ID || "").trim() || "coding-agent";
    this.started = false;
    this.ended = false;
    this.seq = 0;
  }

  /** The identity block embedded in every event. */
  identityBlock() {
    return {
      session: this.session,
      user: this.user,
      user_source: this.userSource,
      tenant: this.tenant,
      device_id: this.deviceId,
    };
  }

  /** Mark the session started exactly once. Returns true the first time so the
   *  caller knows to emit a single session_start event. */
  start() {
    if (this.started) return false;
    this.started = true;
    return true;
  }

  /** Allocate the next tool-call sequence number (0-based). */
  nextSeq() {
    return this.seq++;
  }

  /** Mark the session ended exactly once. Returns true the first time so the
   *  caller knows to emit a single session_end event. */
  end() {
    if (!this.started || this.ended) return false;
    this.ended = true;
    return true;
  }
}
