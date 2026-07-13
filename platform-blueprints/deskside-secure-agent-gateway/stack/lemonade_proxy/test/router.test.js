// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Unit tests for SemanticRouterClient — the consult-only vLLM Semantic Router
// client. No network: fetch is mocked. Covers tier mapping, disabled mode,
// empty prompt, and fail-open on error/timeout.

import { test } from "node:test";
import assert from "node:assert/strict";
import { SemanticRouterClient } from "../src/router.js";

function fakeFetch(response) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, opts });
    if (typeof response === "function") return response(url, opts);
    return response;
  };
  fn.calls = calls;
  return fn;
}

function jsonResponse(obj, ok = true, status = 200) {
  return { ok, status, text: async () => JSON.stringify(obj) };
}

test("disabled router never calls out and stays local", async () => {
  const fetchImpl = fakeFetch(jsonResponse({}));
  const r = new SemanticRouterClient({ enabled: false, fetchImpl });
  const out = await r.route("prove sqrt(2) is irrational");
  assert.equal(out.enabled, false);
  assert.equal(out.tier, "local");
  assert.equal(fetchImpl.calls.length, 0);
});

test("empty prompt stays local without a classify call", async () => {
  const fetchImpl = fakeFetch(jsonResponse({}));
  const r = new SemanticRouterClient({ enabled: true, fetchImpl });
  const out = await r.route("");
  assert.equal(out.enabled, true);
  assert.equal(out.tier, "local");
  assert.equal(fetchImpl.calls.length, 0);
});

test("reasoning prompt -> frontier tier (claude- model)", async () => {
  const fetchImpl = fakeFetch(
    jsonResponse({
      recommended_model: "claude-opus-4.8",
      routing_decision: "frontier-reasoning",
      matched_signals: { complexity: ["needs_reasoning:hard"] },
      classification: { category: "math", confidence: 0.9 },
    }),
  );
  const r = new SemanticRouterClient({ enabled: true, fetchImpl, frontierModel: "claude-opus-4.8" });
  const out = await r.route("prove sqrt(2) is irrational step by step");
  assert.equal(out.tier, "frontier");
  assert.equal(out.reachable, true);
  assert.equal(out.selectedModel, "claude-opus-4.8");
  assert.equal(out.decision, "frontier-reasoning");
  assert.equal(out.complexity, "needs_reasoning:hard");
  // posts to the classify endpoint with the prompt text
  assert.match(fetchImpl.calls[0].url, /\/api\/v1\/classify\/intent$/);
  assert.equal(JSON.parse(fetchImpl.calls[0].opts.body).text, "prove sqrt(2) is irrational step by step");
});

test("simple prompt -> local tier", async () => {
  const fetchImpl = fakeFetch(
    jsonResponse({
      recommended_model: "lemonade-local",
      routing_decision: "local-simple",
      matched_signals: { complexity: ["needs_reasoning:easy"] },
    }),
  );
  const r = new SemanticRouterClient({ enabled: true, fetchImpl });
  const out = await r.route("what is the capital of France?");
  assert.equal(out.tier, "local");
  assert.equal(out.selectedModel, "lemonade-local");
  assert.equal(out.complexity, "needs_reasoning:easy");
});

test("configured frontierModel (non-claude) maps to frontier", async () => {
  const fetchImpl = fakeFetch(jsonResponse({ recommended_model: "big-local-70b" }));
  const r = new SemanticRouterClient({ enabled: true, fetchImpl, frontierModel: "big-local-70b" });
  const out = await r.route("hard prompt");
  assert.equal(out.tier, "frontier");
});

test("fail-open: classify error keeps the request local", async () => {
  const fetchImpl = fakeFetch(async () => {
    throw new Error("connection refused");
  });
  const r = new SemanticRouterClient({ enabled: true, fetchImpl });
  const out = await r.route("anything");
  assert.equal(out.enabled, true);
  assert.equal(out.reachable, false);
  assert.equal(out.tier, "local");
  assert.match(out.error, /connection refused/);
});

test("fail-open: non-200 classify keeps the request local", async () => {
  const fetchImpl = fakeFetch({ ok: false, status: 500, text: async () => "boom" });
  const r = new SemanticRouterClient({ enabled: true, fetchImpl });
  const out = await r.route("anything");
  assert.equal(out.reachable, false);
  assert.equal(out.tier, "local");
});

test("health returns true only on ok response", async () => {
  const up = new SemanticRouterClient({ enabled: true, fetchImpl: fakeFetch({ ok: true }) });
  assert.equal(await up.health(), true);
  const down = new SemanticRouterClient({
    enabled: true,
    fetchImpl: fakeFetch(async () => {
      throw new Error("down");
    }),
  });
  assert.equal(await down.health(), false);
});
