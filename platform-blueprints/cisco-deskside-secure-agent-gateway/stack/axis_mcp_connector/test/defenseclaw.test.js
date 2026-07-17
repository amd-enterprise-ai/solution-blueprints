// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { DefenseClawClient } from "../src/defenseclaw.js";

function fakeFetch(verdict, { ok = true, status = 200 } = {}) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, opts });
    return {
      ok,
      status,
      text: async () => JSON.stringify(verdict),
    };
  };
  fn.calls = calls;
  return fn;
}

test("admit allows a clean tool call and sends correct payload + headers", async () => {
  const f = fakeFetch({ action: "allow", severity: "NONE", findings: [] });
  const c = new DefenseClawClient({ token: "tok", fetchImpl: f });
  const v = await c.admitToolCall({
    session: "s1",
    user: "amd",
    userSource: "os",
    argv: ["bash", "-c", "echo hi"],
    cwd: "/tmp",
  });
  assert.equal(v.decision, "allow");
  assert.equal(v.reachable, true);

  const { url, opts } = f.calls[0];
  assert.match(url, /\/api\/v1\/inspect\/tool$/);
  assert.equal(opts.headers["X-DefenseClaw-Token"], "tok");
  assert.equal(opts.headers["Authorization"], "Bearer tok");
  assert.equal(opts.headers["X-DefenseClaw-Client"], "axis-mcp");
  const body = JSON.parse(opts.body);
  assert.equal(body.tool, "run");
  assert.equal(body.direction, "tool_call");
  assert.equal(body.session_id, "s1");
  // Identity passthrough so DefenseClaw can do per-user policy/logging.
  assert.equal(body.user, "amd");
  assert.equal(body.user_source, "os");
  const args = JSON.parse(body.args);
  assert.deepEqual(args.argv, ["bash", "-c", "echo hi"]);
});

test("admit blocks on explicit block action", async () => {
  const f = fakeFetch({ action: "block", severity: "HIGH", findings: ["SSH-KEY-READ"] });
  const c = new DefenseClawClient({ fetchImpl: f });
  const v = await c.admitToolCall({ session: "s", user: "alice", userSource: "env", argv: ["bash", "-c", "cat ~/.ssh/id_ed25519"] });
  assert.equal(v.decision, "block");
  assert.equal(v.severity, "HIGH");
  assert.deepEqual(v.findings, ["SSH-KEY-READ"]);
  // user/userSource must be forwarded even on block path.
  const body = JSON.parse(f.calls[0].opts.body);
  assert.equal(body.user, "alice");
  assert.equal(body.user_source, "env");
});

test("action mode blocks HIGH/CRITICAL even if action says allow (belt-and-braces)", async () => {
  const f = fakeFetch({ action: "allow", severity: "CRITICAL", findings: ["X"] });
  const c = new DefenseClawClient({ mode: "action", fetchImpl: f });
  const v = await c.admitToolCall({ session: "s", user: "alice", userSource: "os", argv: [] });
  assert.equal(v.decision, "block");
});

test("observe mode does not block; surfaces would_block", async () => {
  const f = fakeFetch({ action: "allow", severity: "HIGH", findings: ["X"], would_block: true });
  const c = new DefenseClawClient({ mode: "observe", fetchImpl: f });
  const v = await c.admitToolCall({ session: "s", user: "alice", userSource: "os", argv: [] });
  assert.equal(v.decision, "allow");
  assert.equal(v.wouldBlock, true);
});

test("unreachable gateway -> fail-closed blocks by default", async () => {
  const f = async () => {
    throw new Error("ECONNREFUSED");
  };
  const c = new DefenseClawClient({ fetchImpl: f });
  const v = await c.admitToolCall({ session: "s", user: "alice", userSource: "os", argv: [] });
  assert.equal(v.decision, "block");
  assert.equal(v.reachable, false);
  assert.match(v.findings[0], /gateway-unreachable/);
});

test("unreachable gateway -> fail-open allows when configured", async () => {
  const f = async () => {
    throw new Error("ECONNREFUSED");
  };
  const c = new DefenseClawClient({ failOpen: true, fetchImpl: f });
  const v = await c.admitToolCall({ session: "s", user: "alice", userSource: "os", argv: [] });
  assert.equal(v.decision, "allow");
  assert.equal(v.reachable, false);
});

test("inspectToolResult sends identity and swallows errors on failure", async () => {
  const f = async () => {
    throw new Error("down");
  };
  const c = new DefenseClawClient({ fetchImpl: f });
  const v = await c.inspectToolResult({ session: "s", user: "alice", userSource: "os", content: "out" });
  assert.equal(v, null);
});

test("inspectToolResult sends user + user_source in the POST body", async () => {
  const f = fakeFetch({ action: "allow", severity: "NONE", findings: [] });
  const c = new DefenseClawClient({ fetchImpl: f });
  await c.inspectToolResult({ session: "s", user: "alice", userSource: "env", content: "output text" });
  const body = JSON.parse(f.calls[0].opts.body);
  assert.equal(body.direction, "tool_result");
  assert.equal(body.user, "alice");
  assert.equal(body.user_source, "env");
});

test("health returns boolean", async () => {
  const okFetch = async () => ({ ok: true });
  const badFetch = async () => {
    throw new Error("x");
  };
  assert.equal(await new DefenseClawClient({ fetchImpl: okFetch }).health(), true);
  assert.equal(await new DefenseClawClient({ fetchImpl: badFetch }).health(), false);
});
