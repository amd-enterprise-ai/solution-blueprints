// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { DefenseClawInferenceClient } from "../src/defenseclaw.js";

function fakeFetch(verdict, { ok = true, status = 200 } = {}) {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts });
    return { ok, status, text: async () => JSON.stringify(verdict) };
  };
  return { fetchImpl, calls };
}

test("inspectRequest posts to /api/v1/inspect/request and normalizes allow", async () => {
  const { fetchImpl, calls } = fakeFetch({ action: "allow", severity: "NONE", findings: [] });
  const c = new DefenseClawInferenceClient({ fetchImpl });
  const v = await c.inspectRequest({ session: "s1", user: "amd", userSource: "os", model: "m", content: "hi" });
  assert.match(calls[0].url, /\/api\/v1\/inspect\/request$/);
  const body = JSON.parse(calls[0].opts.body);
  assert.equal(body.session_id, "s1");
  assert.equal(body.content, "hi");
  // Identity passthrough for per-user policy/logging.
  assert.equal(body.user, "amd");
  assert.equal(body.user_source, "os");
  assert.equal(v.decision, "allow");
  assert.equal(v.reachable, true);
});

test("inspectResponse posts to /api/v1/inspect/response with identity", async () => {
  const { fetchImpl, calls } = fakeFetch({ action: "allow", severity: "LOW", findings: ["X"], would_block: true });
  const c = new DefenseClawInferenceClient({ fetchImpl });
  const v = await c.inspectResponse({ session: "s1", user: "alice", userSource: "env", model: "m", content: "secret" });
  assert.match(calls[0].url, /\/api\/v1\/inspect\/response$/);
  const body = JSON.parse(calls[0].opts.body);
  assert.equal(body.user, "alice");
  assert.equal(body.user_source, "env");
  assert.equal(v.severity, "LOW");
  assert.deepEqual(v.findings, ["X"]);
  assert.equal(v.wouldBlock, true);
  assert.equal(v.decision, "allow"); // observe mode never blocks
});

test("action mode blocks HIGH severity", async () => {
  const { fetchImpl } = fakeFetch({ action: "allow", severity: "HIGH", findings: ["INJ"] });
  const c = new DefenseClawInferenceClient({ fetchImpl, mode: "action" });
  const v = await c.inspectRequest({ session: "s", user: "alice", userSource: "os", model: "m", content: "x" });
  assert.equal(v.decision, "block");
});

test("gateway raw block maps to block", async () => {
  const { fetchImpl } = fakeFetch({ action: "block", severity: "CRITICAL", findings: ["LEAK"] });
  const c = new DefenseClawInferenceClient({ fetchImpl, mode: "observe" });
  const v = await c.inspectResponse({ session: "s", user: "alice", userSource: "os", model: "m", content: "x" });
  assert.equal(v.decision, "block");
});

test("unreachable gateway fails OPEN by default", async () => {
  const fetchImpl = async () => {
    throw new Error("down");
  };
  const c = new DefenseClawInferenceClient({ fetchImpl });
  const v = await c.inspectRequest({ session: "s", user: "alice", userSource: "os", model: "m", content: "x" });
  assert.equal(v.decision, "allow");
  assert.equal(v.reachable, false);
  assert.match(v.findings[0], /gateway-unreachable/);
});

test("unreachable gateway can fail closed when configured", async () => {
  const fetchImpl = async () => {
    throw new Error("down");
  };
  const c = new DefenseClawInferenceClient({ fetchImpl, failOpen: false });
  const v = await c.inspectRequest({ session: "s", user: "alice", userSource: "os", model: "m", content: "x" });
  assert.equal(v.decision, "block");
});

test("empty content is not inspected", async () => {
  const { fetchImpl, calls } = fakeFetch({ action: "allow" });
  const c = new DefenseClawInferenceClient({ fetchImpl });
  const v = await c.inspectRequest({ session: "s", user: "alice", userSource: "os", model: "m", content: "" });
  assert.equal(v, null);
  assert.equal(calls.length, 0);
});
