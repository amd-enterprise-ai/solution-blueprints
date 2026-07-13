// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Inference-plane session identity for the Lemonade telemetry proxy.
//
// This mirrors the connector's identity.js so both planes land the SAME identity
// block in Splunk and correlate by identity.session. One proxy process serves
// one logical agent session; the session id is injected via LLM_SESSION (set to
// the same value the connector gets in AXIS_SESSION so the tool plane and the
// inference plane line up), otherwise a fresh lp-<uuid> is minted.

import { randomUUID } from "node:crypto";
import { hostname } from "node:os";

export function makeSessionId(envSession) {
  if (envSession && envSession.trim()) return envSession.trim();
  return `lp-${randomUUID()}`;
}

/** Holds the identity of one inference session and hands out per-request
 *  sequence numbers. Pure/in-memory; the llm_events layer emits the events. */
export class ProxyIdentity {
  constructor(env = process.env) {
    this.session = makeSessionId(env.LLM_SESSION || env.AXIS_SESSION);
    this.user = (env.LLM_USER || env.AXIS_USER || "").trim() || "unknown";
    this.tenant = (env.LLM_TENANT || env.AXIS_TENANT || "").trim() || "client-deskside";
    this.deviceId = (env.LLM_DEVICE_ID || env.AXIS_DEVICE_ID || "").trim() || hostnameSafe();
    this.policySource = (env.LLM_POLICY_SOURCE || "").trim() || "local-control";
    this.policyId = (env.LLM_POLICY_ID || "").trim() || "inference-proxy";
    this.started = false;
    this.ended = false;
    this.seq = 0;
  }

  identityBlock() {
    return {
      session: this.session,
      user: this.user,
      tenant: this.tenant,
      device_id: this.deviceId,
    };
  }

  start() {
    if (this.started) return false;
    this.started = true;
    return true;
  }

  nextSeq() {
    return this.seq++;
  }

  end() {
    if (!this.started || this.ended) return false;
    this.ended = true;
    return true;
  }
}

function hostnameSafe() {
  try {
    return hostname();
  } catch {
    return "localhost";
  }
}
