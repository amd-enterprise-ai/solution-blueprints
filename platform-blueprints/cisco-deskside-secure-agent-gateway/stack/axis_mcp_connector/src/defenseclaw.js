// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// DefenseClaw gateway REST client.
//
// Cisco DefenseClaw (github.com/cisco-ai-defense/defenseclaw, Apache-2.0) is a
// governance shell for agentic AI: admission control, runtime guardrails on
// live tool_call/tool_result traffic (regex/policy/CodeGuard/optional LLM
// judge), and observe-vs-action modes. Its Go gateway sidecar exposes a REST
// API on :18970.
//
// This connector is a DefenseClaw *enforcement client*: before AXIS runs a tool
// call we POST it to /api/v1/inspect/tool and read the verdict. In `action`
// mode a HIGH/CRITICAL block stops execution (AXIS never runs it); in `observe`
// mode the gateway downgrades the action to "allow" and sets would_block, so we
// only log it. After execution we optionally POST the result to
// /api/v1/inspect/tool with direction=tool_result for output scanning.
//
// Request/response shapes mirror internal/gateway/inspect.go:
//   ToolInspectRequest  { tool, args, content, direction, session_id, connector }
//   ToolInspectVerdict  { action, raw_action, severity, findings, would_block, reason, mode }

const BLOCK_SEVERITIES = new Set(["HIGH", "CRITICAL"]);

export class DefenseClawClient {
  constructor({
    baseUrl,
    token,
    mode,
    failOpen,
    connector,
    timeoutMs,
    fetchImpl,
  } = {}) {
    this.baseUrl = (baseUrl || "http://127.0.0.1:18970").replace(/\/+$/, "");
    this.token = token || "";
    // action: HIGH/CRITICAL blocks execution. observe: log only.
    this.mode = (mode || "action").toLowerCase();
    // When the gateway is unreachable, fail-open allows the call (logged as
    // unknown); fail-closed blocks it. Default fail-closed for safety.
    this.failOpen = Boolean(failOpen);
    this.connector = connector || "axis-mcp";
    this.timeoutMs = timeoutMs || 5_000;
    this.fetch = fetchImpl || globalThis.fetch;
  }

  #headers() {
    const h = { "content-type": "application/json", "X-DefenseClaw-Client": "axis-mcp" };
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
      if (!res.ok) {
        throw new Error(`defenseclaw ${path} -> ${res.status} ${text}`);
      }
      return text ? JSON.parse(text) : {};
    } finally {
      clearTimeout(timer);
    }
  }

  /** Admit a tool call. Returns a normalized decision:
   *   { decision: "allow"|"block", severity, findings, wouldBlock, reason,
   *     reachable: bool, raw }
   *  `decision` already accounts for mode + fail-open: it is what the caller
   *  should act on (block ⇒ do not run AXIS). */
  async admitToolCall({ session, user, userSource, tool = "run", argv, cwd }) {
    const args = { argv, cwd };
    try {
      const verdict = await this.#post("/api/v1/inspect/tool", {
        tool,
        args: JSON.stringify(args),
        direction: "tool_call",
        session_id: session,
        // Identity passthrough so DefenseClaw can do per-user policy/logging.
        // Asserted, not verified (no auth yet) — user_source records the trust
        // level; DefenseClaw is a consumer of identity, never its producer.
        user,
        user_source: userSource,
        connector: this.connector,
      });
      return this.#normalize(verdict);
    } catch (err) {
      return this.#unreachable(err);
    }
  }

  /** Optionally inspect a tool result (observe lane). Failures are swallowed —
   *  result inspection never blocks a call that already ran. */
  async inspectToolResult({ session, user, userSource, tool = "run", content }) {
    try {
      const verdict = await this.#post("/api/v1/inspect/tool", {
        tool,
        content,
        direction: "tool_result",
        session_id: session,
        user,
        user_source: userSource,
        connector: this.connector,
      });
      return this.#normalize(verdict);
    } catch {
      return null;
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

  /** Map a gateway verdict to our allow/block decision. The gateway has already
   *  applied its mode (observe downgrades action to "allow" + sets
   *  would_block), so we trust verdict.action for the live decision but also
   *  enforce our own action-mode block on HIGH/CRITICAL as a belt-and-braces
   *  check in case mode wiring differs. */
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
