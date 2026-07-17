// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// vLLM Semantic Router client — the per-prompt routing decision.
//
// A full router data plane runs Envoy + ExtProc to pick a model inline for every
// OpenAI request. We do NOT want the proxy to stop being a transparent
// byte-for-byte data path, so we only CONSULT the router: its api server exposes
// a standalone classify endpoint that returns a routing decision for a prompt
// WITHOUT running any inference and WITHOUT going through Envoy.
//
//   POST /api/v1/classify/intent  { text }
//     -> { recommended_model, routing_decision,
//          matched_signals:{ complexity:[...], domains:[...] },
//          classification:{ category, confidence } }
//   GET  /health  -> { status:"healthy" }
//
// (semantic-router: pkg/apiserver/route_classify.go, structs in
//  pkg/services/classification_signal_types.go.)
//
// The difficulty-based config (see the router config under the A/B test) makes
// the decision engine return the frontier model NAME for hard/reasoning prompts
// and the local model NAME for simple ones. We map that name to a tier and let server.js send
// the request to Lemonade (local) or the frontier gateway.
//
// Fail-OPEN by default: a router
// hiccup must never take inference down — an unreachable/slow router just means
// the request stays on the local tier.

export class SemanticRouterClient {
  constructor({ enabled, apiUrl, frontierModel, timeoutMs, fetchImpl } = {}) {
    this.enabled = Boolean(enabled);
    this.apiUrl = (apiUrl || "http://127.0.0.1:8088").replace(/\/+$/, "");
    this.frontierModel = frontierModel || "claude-opus-4.8";
    this.timeoutMs = timeoutMs || 5_000;
    this.fetch = fetchImpl || globalThis.fetch;
  }

  /** Map a router-selected model NAME to a routing tier. Frontier models are the
   *  Claude family (name starts with "claude-") or the configured frontier id. */
  #tierFor(model) {
    const m = String(model || "");
    return m.startsWith("claude-") || m === this.frontierModel ? "frontier" : "local";
  }

  async health() {
    try {
      const res = await this.fetch(`${this.apiUrl}/health`);
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Ask the router which tier should serve this prompt. Never throws. */
  async route(promptText) {
    if (!this.enabled) {
      return { enabled: false, reachable: false, tier: "local", decision: null, complexity: null, selectedModel: null, classifyMs: null };
    }
    if (!promptText) {
      // Nothing to classify -> keep it local (cheap, transparent).
      return { enabled: true, reachable: false, tier: "local", decision: null, complexity: null, selectedModel: null, classifyMs: null };
    }
    const started = Date.now();
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await this.fetch(`${this.apiUrl}/api/v1/classify/intent`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: promptText }),
        signal: ctrl.signal,
      });
      const text = await res.text().catch(() => "");
      if (!res.ok) throw new Error(`router classify -> ${res.status} ${text}`);
      const body = text ? JSON.parse(text) : {};
      const selectedModel = body.recommended_model || null;
      const decision = body.routing_decision || null;
      const complexity = complexityOf(body);
      return {
        enabled: true,
        reachable: true,
        tier: this.#tierFor(selectedModel),
        decision,
        complexity,
        selectedModel,
        classifyMs: Date.now() - started,
      };
    } catch (err) {
      // Fail open: on any error/timeout, keep the request on the local tier.
      return {
        enabled: true,
        reachable: false,
        tier: "local",
        decision: null,
        complexity: null,
        selectedModel: null,
        classifyMs: Date.now() - started,
        error: String(err && err.message ? err.message : err),
      };
    } finally {
      clearTimeout(timer);
    }
  }
}

/** Best-effort pull of the complexity signal from a classify response. Prefers
 *  the dedicated matched complexity signal, falls back to the intent category. */
function complexityOf(body) {
  const ms = body.matched_signals;
  if (ms && Array.isArray(ms.complexity) && ms.complexity.length) {
    return ms.complexity.join(",");
  }
  if (body.classification && body.classification.category) {
    return String(body.classification.category);
  }
  return null;
}
