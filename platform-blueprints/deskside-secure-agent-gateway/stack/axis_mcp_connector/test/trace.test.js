// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { newTraceId, newSpanId, TraceReader, traceStatePath } from "../src/trace.js";

test("trace/span ids use OTEL hex format", () => {
  assert.match(newTraceId(), /^[0-9a-f]{32}$/);
  assert.match(newSpanId(), /^[0-9a-f]{16}$/);
});

test("TraceReader reads the trace the proxy wrote to the statefile", async () => {
  const dir = await mkdtemp(join(tmpdir(), "ctrace-"));
  try {
    const path = join(dir, "t.json");
    const env = { AXIS_TRACE_STATE: path };
    await writeFile(
      path,
      JSON.stringify({ session: "sess", trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 3 }),
    );
    const r = new TraceReader("sess", env);
    const cur = r.current();
    assert.equal(cur.trace_id, "a".repeat(32));
    assert.equal(cur.root_span_id, "b".repeat(16));
    assert.equal(cur.turn, 3);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("TraceReader picks up statefile updates (new turn) on the next read", async () => {
  const dir = await mkdtemp(join(tmpdir(), "ctrace-"));
  try {
    const path = join(dir, "t.json");
    const env = { AXIS_TRACE_STATE: path };
    await writeFile(path, JSON.stringify({ trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 0 }));
    const r = new TraceReader("sess", env);
    assert.equal(r.current().turn, 0);
    await writeFile(path, JSON.stringify({ trace_id: "c".repeat(32), root_span_id: "d".repeat(16), turn: 1 }));
    assert.equal(r.current().trace_id, "c".repeat(32));
    assert.equal(r.current().turn, 1);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("TraceReader mints a stable fallback trace when no statefile exists", () => {
  const env = { AXIS_TRACE_STATE: "/tmp/csi-no-such-trace-file.json" };
  const r = new TraceReader("sess", env);
  const a = r.current();
  const b = r.current();
  assert.match(a.trace_id, /^[0-9a-f]{32}$/);
  assert.equal(a.trace_id, b.trace_id, "fallback trace is stable across calls");
});

test("connector and proxy resolve the SAME statefile path for a session", () => {
  const env = { TMPDIR: "/tmp" };
  assert.equal(traceStatePath("cc-x", env), "/tmp/axis-trace-cc-x.json");
});
