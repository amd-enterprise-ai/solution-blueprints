// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { newTraceId, newSpanId, TraceState, readTraceState, traceStatePath } from "../src/trace.js";
import { isNewUserTurn } from "../src/anthropic.js";

test("trace/span ids use OTEL hex format (32 / 16 chars)", () => {
  assert.match(newTraceId(), /^[0-9a-f]{32}$/);
  assert.match(newSpanId(), /^[0-9a-f]{16}$/);
});

test("traceStatePath honors AXIS_TRACE_STATE override", () => {
  assert.equal(traceStatePath("s", { AXIS_TRACE_STATE: "/tmp/x.json" }), "/tmp/x.json");
});

test("traceStatePath derives a session-safe default path", () => {
  const p = traceStatePath("cc-a/b c", { TMPDIR: "/tmp" });
  assert.equal(p, "/tmp/axis-trace-cc-a_b_c.json");
});

test("startTurn mints a new trace + root span and bumps the turn", async () => {
  const dir = await mkdtemp(join(tmpdir(), "trace-"));
  try {
    const env = { AXIS_TRACE_STATE: join(dir, "t.json") };
    const ts = new TraceState("sess", env);
    const t0 = ts.startTurn();
    assert.equal(t0.turn, 0);
    assert.match(t0.trace_id, /^[0-9a-f]{32}$/);
    const t1 = ts.startTurn();
    assert.equal(t1.turn, 1);
    assert.notEqual(t0.trace_id, t1.trace_id);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("ensure() creates a trace once, then reuses it (no turn bump)", async () => {
  const dir = await mkdtemp(join(tmpdir(), "trace-"));
  try {
    const env = { AXIS_TRACE_STATE: join(dir, "t.json") };
    const ts = new TraceState("sess", env);
    const a = ts.ensure();
    const b = ts.ensure();
    assert.equal(a.trace_id, b.trace_id);
    assert.equal(a.turn, 0);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("statefile is persisted and readable by the tool plane's reader", async () => {
  const dir = await mkdtemp(join(tmpdir(), "trace-"));
  try {
    const env = { AXIS_TRACE_STATE: join(dir, "t.json") };
    const ts = new TraceState("sess", env);
    const t = ts.startTurn();
    const onDisk = JSON.parse(await readFile(env.AXIS_TRACE_STATE, "utf8"));
    assert.equal(onDisk.trace_id, t.trace_id);
    assert.equal(onDisk.root_span_id, t.root_span_id);
    assert.equal(onDisk.session, "sess");
    // readTraceState is what the connector uses.
    const read = readTraceState("sess", env);
    assert.equal(read.trace_id, t.trace_id);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("readTraceState returns null when no statefile exists", () => {
  assert.equal(readTraceState("nope", { AXIS_TRACE_STATE: "/tmp/does-not-exist-xyz.json" }), null);
});

// --- turn detection (isNewUserTurn) --------------------------------------
test("a fresh string user prompt is a new turn", () => {
  assert.equal(isNewUserTurn({ messages: [{ role: "user", content: "fix the bug" }] }), true);
});

test("a tool_result continuation is NOT a new turn", () => {
  const body = {
    messages: [
      { role: "user", content: "fix the bug" },
      { role: "assistant", content: [{ type: "tool_use", id: "t1", name: "run", input: {} }] },
      { role: "user", content: [{ type: "tool_result", tool_use_id: "t1", content: "ok" }] },
    ],
  };
  assert.equal(isNewUserTurn(body), false);
});

test("a new human message after a tool loop IS a new turn", () => {
  const body = {
    messages: [
      { role: "user", content: "fix the bug" },
      { role: "assistant", content: [{ type: "tool_use", id: "t1", name: "run", input: {} }] },
      { role: "user", content: [{ type: "tool_result", tool_use_id: "t1", content: "ok" }] },
      { role: "assistant", content: "done" },
      { role: "user", content: "now add a test" },
    ],
  };
  assert.equal(isNewUserTurn(body), true);
});

test("empty/garbled body defaults to a new turn (trace always exists)", () => {
  assert.equal(isNewUserTurn({}), true);
  assert.equal(isNewUserTurn({ messages: [] }), true);
});

test("last message from assistant is not a new user turn", () => {
  assert.equal(
    isNewUserTurn({ messages: [{ role: "user", content: "hi" }, { role: "assistant", content: "yo" }] }),
    false,
  );
});
