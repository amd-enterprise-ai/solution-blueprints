// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { SessionIdentity } from "../src/identity.js";
import {
  SplunkEventSink,
  buildSessionStart,
  buildSessionEnd,
  buildToolCall,
} from "../src/splunk_events.js";

function id() {
  return new SessionIdentity({
    AXIS_SESSION: "sess-1",
    AXIS_USER: "alice",
    AXIS_TENANT: "acme",
    AXIS_DEVICE_ID: "dev-9",
    AXIS_POLICY_SOURCE: "local-control",
    AXIS_POLICY_ID: "coding-agent",
  });
}

test("session_start carries identity + policy provenance", () => {
  const e = buildSessionStart(id());
  assert.equal(e.event, "axis.session_start");
  assert.equal(e.identity.session, "sess-1");
  assert.equal(e.identity.user, "alice");
  assert.equal(e.policy.source, "local-control");
  assert.equal(e.policy.id, "coding-agent");
  assert.equal(typeof e.time, "number");
});

test("session_end carries identity", () => {
  const e = buildSessionEnd(id());
  assert.equal(e.event, "axis.session_end");
  assert.equal(e.identity.session, "sess-1");
});

test("toolcall event schema is stable (command/decision/result/defenseclaw)", () => {
  const e = buildToolCall({
    identity: id(),
    seq: 2,
    argv: ["bash", "-c", "curl --token abc x"],
    argvRedacted: ["bash", "-c", "curl --token <redacted> x"],
    decision: "allow",
    result: { code: 0, durationMs: 12, timedOut: false },
    defenseclaw: { decision: "allow", severity: "NONE", findings: [], wouldBlock: false, reachable: true },
  });
  assert.equal(e.event, "axis.toolcall");
  assert.equal(e.command.seq, 2);
  assert.deepEqual(e.command.argv_redacted, ["bash", "-c", "curl --token <redacted> x"]);
  assert.equal(e.decision, "allow");
  assert.equal(e.result.exit, 0);
  assert.equal(e.result.duration_ms, 12);
  assert.equal(e.defenseclaw.action, "allow");
  assert.equal(e.defenseclaw.severity, "NONE");
});

test("toolcall carries OTEL envelope + per-turn trace/span", () => {
  const trace = { trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 2 };
  const e = buildToolCall({
    identity: id(),
    seq: 1,
    argv: ["bash", "-c", "echo hi"],
    argvRedacted: ["bash", "-c", "echo hi"],
    decision: "allow",
    result: { code: 0, durationMs: 5, timedOut: false },
    defenseclaw: { decision: "allow", severity: "NONE", findings: [], wouldBlock: false, reachable: true },
    trace,
  });
  assert.match(e.event_id, /^[0-9a-f-]{36}$/);
  assert.equal(e.schema_version, "1.0");
  assert.equal(e.ingest_source, "axis-mcp");
  assert.equal(e.trace_id, "a".repeat(32));
  assert.match(e.span_id, /^[0-9a-f]{16}$/);
  assert.equal(e.parent_span_id, "b".repeat(16));
  assert.equal(e.resource["service.name"], "axis-mcp-connector");
  assert.equal(e.resource["service.instance.id"], "dev-9");
  assert.equal(e.attributes["axis.turn"], 2);
  assert.equal(e.attributes["tool.name"], "run");
});

test("session_start is session-scoped: trace_id null, has event_id + resource", () => {
  const e = buildSessionStart(id());
  assert.equal(e.trace_id, null);
  assert.equal(e.span_id, null);
  assert.match(e.event_id, /^[0-9a-f-]{36}$/);
  assert.equal(e.resource["service.name"], "axis-mcp-connector");
});

test("toolcall with no result (blocked) has null exit", () => {
  const e = buildToolCall({
    identity: id(),
    seq: 0,
    argv: ["bash", "-c", "x"],
    argvRedacted: ["bash", "-c", "x"],
    decision: "block",
    result: null,
    defenseclaw: { decision: "block", severity: "HIGH", findings: ["X"], wouldBlock: true, reachable: true },
  });
  assert.equal(e.decision, "block");
  assert.equal(e.result.exit, null);
  assert.equal(e.defenseclaw.action, "block");
});

test("sink appends JSONL to file", async () => {
  const dir = await mkdtemp(join(tmpdir(), "sink-"));
  const path = join(dir, "events.jsonl");
  try {
    const sink = new SplunkEventSink({ sinkPath: path });
    await sink.emit(buildSessionStart(id()));
    await sink.emit(buildToolCall({
      identity: id(),
      seq: 0,
      argv: ["bash", "-c", "echo hi"],
      argvRedacted: ["bash", "-c", "echo hi"],
      decision: "allow",
      result: { code: 0, durationMs: 1, timedOut: false },
      defenseclaw: { decision: "allow", severity: "NONE", findings: [], wouldBlock: false, reachable: true },
    }));
    const lines = (await readFile(path, "utf8")).trim().split("\n");
    assert.equal(lines.length, 2);
    assert.equal(JSON.parse(lines[0]).event, "axis.session_start");
    assert.equal(JSON.parse(lines[1]).event, "axis.toolcall");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("sink posts HEC envelope with Splunk auth header", async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts });
    return { ok: true, status: 200, text: async () => "{}" };
  };
  const sink = new SplunkEventSink({ hecUrl: "http://127.0.0.1:18088", hecToken: "tok", fetchImpl });
  await sink.emit(buildSessionStart(id()));
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/services\/collector\/event$/);
  assert.equal(calls[0].opts.headers.Authorization, "Splunk tok");
  const env = JSON.parse(calls[0].opts.body);
  assert.equal(env.sourcetype, "axis:toolcall");
  assert.equal(env.index, "axis");
  assert.equal(env.event.event, "axis.session_start");
});

test("sink HEC failure does not throw", async () => {
  const fetchImpl = async () => {
    throw new Error("down");
  };
  const sink = new SplunkEventSink({ hecUrl: "http://127.0.0.1:1", fetchImpl });
  await sink.emit(buildSessionEnd(id())); // must resolve
});

test("reachable() returns true when no HEC is configured", async () => {
  const sink = new SplunkEventSink({ sinkPath: "/tmp/none.jsonl" });
  assert.equal(await sink.reachable(), true);
});

test("reachable() times out and returns false when the HEC hangs", async () => {
  // fetch never resolves on its own; it only rejects when the abort signal fires.
  const fetchImpl = (url, opts) =>
    new Promise((_, reject) => {
      opts.signal.addEventListener("abort", () => reject(new Error("aborted")));
    });
  const sink = new SplunkEventSink({
    hecUrl: "http://127.0.0.1:1",
    fetchImpl,
    reachableTimeoutMs: 20,
  });
  const t0 = Date.now();
  assert.equal(await sink.reachable(), false);
  assert.ok(Date.now() - t0 < 1000, "should fail fast via timeout, not hang");
});
