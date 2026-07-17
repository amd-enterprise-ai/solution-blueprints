// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// DefenseClaw inference-plane client.
//
// The connector governs the TOOL plane via /api/v1/inspect/tool. DefenseClaw
// also ships the INFERENCE-plane endpoints this proxy uses:
//   POST /api/v1/inspect/request   direction=prompt      — scan the user prompt
//   POST /api/v1/inspect/response  direction=completion  — scan the LLM output
// (internal/gateway/inspect_hooks.go: RequestInspectRequest/ResponseInspectRequest
//  -> ToolInspectVerdict {action, severity, findings, would_block, reason, mode}).
//
// Policy choices for the inference plane (see README):
//  * observe by default — a false-positive on a prompt must not kill a chat turn.
//    DefenseClaw itself already demotes prompt-surface blocks to "alert"; we keep
//    would_block in the event so Cisco can tune before flipping to action mode.
//  * fail-OPEN by default — a governance-sidecar hiccup must never take inference
//    down. (The tool plane defaults fail-closed; the inference plane does not.)

const BLOCK_SEVERITIES = new Set(["HIGH", "CRITICAL"]);

export class DefenseClawInferenceClient {
  constructor({ baseUrl, token, mode, failOpen, timeoutMs, fetchImpl } = {}) {
    this.baseUrl = (baseUrl || "http://127.0.0.1:18970").replace(/\/+$/, "");
    this.token = token || "";
    this.mode = (mode || "observe").toLowerCase();
    this.failOpen = failOpen === undefined ? true : Boolean(failOpen);
    this.timeoutMs = timeoutMs || 5_000;
    this.fetch = fetchImpl || globalThis.fetch;
  }

  #headers() {
    const h = { "content-type": "application/json", "X-DefenseClaw-Client": "lemonade-proxy" };
    if (this.token) {
      h["X-DefenseClaw-Token"] = this.token;
      h["Authorization"] = `Bearer ${this.token}`;
    }
    return h;
  }

  async #post(path, body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await this.fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: this.#headers(),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      const text = await res.text().catch(() => "");
      if (!res.ok) throw new Error(`defenseclaw ${path} -> ${res.status} ${text}`);
      return text ? JSON.parse(text) : {};
    } finally {
      clearTimeout(timer);
    }
  }

  /** Scan the prompt before it reaches the model. */
  async inspectRequest({ session, user, userSource, model, content }) {
    if (!content) return null;
    try {
      const verdict = await this.#post("/api/v1/inspect/request", {
        content,
        model,
        session_id: session,
        // Identity passthrough for per-user policy/logging (asserted, not
        // verified — user_source records the trust level).
        user,
        user_source: userSource,
      });
      return this.#normalize(verdict);
    } catch (err) {
      return this.#unreachable(err);
    }
  }

  /** Scan the completion after the model returns. */
  async inspectResponse({ session, user, userSource, model, content }) {
    if (!content) return null;
    try {
      const verdict = await this.#post("/api/v1/inspect/response", {
        content,
        model,
        session_id: session,
        user,
        user_source: userSource,
      });
      return this.#normalize(verdict);
    } catch (err) {
      return this.#unreachable(err);
    }
  }

  async health() {
    try {
      const res = await this.fetch(`${this.baseUrl}/health`);
      return res.ok;
    } catch {
      return false;
    }
  }

  #normalize(verdict) {
    const action = String(verdict.action || "allow").toLowerCase();
    const severity = String(verdict.severity || "NONE").toUpperCase();
    const findings = Array.isArray(verdict.findings) ? verdict.findings : [];
    const wouldBlock = Boolean(verdict.would_block);
    let decision = "allow";
    if (action === "block") decision = "block";
    if (this.mode === "action" && BLOCK_SEVERITIES.has(severity)) decision = "block";
    return {
      decision,
      severity,
      findings,
      wouldBlock,
      reason: verdict.reason || "",
      reachable: true,
      raw: verdict,
    };
  }

  #unreachable(err) {
    // Inference plane fails open by default: allow, but record it.
    return {
      decision: this.failOpen ? "allow" : "block",
      severity: "UNKNOWN",
      findings: [`gateway-unreachable: ${err.message}`],
      wouldBlock: !this.failOpen,
      reason: "defenseclaw gateway unreachable",
      reachable: false,
      raw: null,
    };
  }
}
