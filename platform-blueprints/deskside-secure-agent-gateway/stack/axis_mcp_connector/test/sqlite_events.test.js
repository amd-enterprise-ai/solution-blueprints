// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import Database from "better-sqlite3";

import { SessionIdentity } from "../src/identity.js";
import {
  SqliteEventSink,
  buildSessionStart,
  buildSessionEnd,
  buildToolCall,
} from "../src/sqlite_events.js";

function id() {
  return new SessionIdentity({
    AXIS_SESSION: "sess-sqlite-1",
    AXIS_USER: "alice",
    AXIS_TENANT: "amd-corp",
    AXIS_DEVICE_ID: "dev-7",
    AXIS_POLICY_SOURCE: "local-control",
    AXIS_POLICY_ID: "coding-agent",
  });
}

// ---------------------------------------------------------------------------
// Event builder shape tests (no DB needed)
// ---------------------------------------------------------------------------

test("buildSessionStart carries identity + policy", () => {
  const e = buildSessionStart(id());
  assert.equal(e.event, "axis.session_start");
  assert.equal(e.identity.session, "sess-sqlite-1");
  assert.equal(e.identity.user, "alice");
  assert.equal(e.policy.source, "local-control");
  assert.equal(e.policy.id, "coding-agent");
  assert.equal(typeof e.time, "number");
});

test("buildSessionEnd carries identity", () => {
  const e = buildSessionEnd(id());
  assert.equal(e.event, "axis.session_end");
  assert.equal(e.identity.session, "sess-sqlite-1");
});

test("buildToolCall has no admission/defenseclaw block and never persists raw argv", () => {
  const e = buildToolCall({
    identity: id(),
    seq: 3,
    argvRedacted: ["bash", "-c", "echo hello"],
    decision: "allow",
    result: { code: 0, durationMs: 10, timedOut: false },
  });
  assert.equal(e.event, "axis.toolcall");
  assert.equal(e.command.seq, 3);
  assert.equal(e.decision, "allow");
  assert.equal(e.result.exit, 0);
  assert.equal(e.result.duration_ms, 10);
  // No pre-execution gate blocks remain — AXIS is the sole enforcement layer.
  assert.ok(!("admission" in e), "event must not have admission block");
  assert.ok(!("defenseclaw" in e), "event must not have defenseclaw block");
  // Only the redacted argv is persisted — never the raw command.
  assert.deepEqual(e.command.argv_redacted, ["bash", "-c", "echo hello"]);
  assert.ok(!("argv" in e.command), "event must not persist raw argv");
});

test("buildToolCall error shape: non-zero exit recorded as 'error', not 'deny'", () => {
  const e = buildToolCall({
    identity: id(),
    seq: 0,
    argvRedacted: ["bash", "-c", "cat ~/.ssh/id_rsa"],
    decision: "error",
    result: { code: 1, durationMs: 12, timedOut: false },
  });
  assert.equal(e.decision, "error");
  assert.equal(e.result.exit, 1);
});

test("buildToolCall block shape: null result → null exit", () => {
  const e = buildToolCall({
    identity: id(),
    seq: 1,
    argvRedacted: ["bash", "-c", "ls"],
    decision: "block",
    result: null,
  });
  assert.equal(e.decision, "block");
  assert.equal(e.result.exit, null);
});

test("buildToolCall carries OTEL envelope fields", () => {
  const trace = { trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 1 };
  const e = buildToolCall({
    identity: id(),
    seq: 1,
    argvRedacted: ["bash", "-c", "echo hi"],
    decision: "allow",
    result: { code: 0, durationMs: 5, timedOut: false },
    trace,
  });
  assert.match(e.event_id, /^[0-9a-f-]{36}$/);
  assert.equal(e.trace_id, "a".repeat(32));
  assert.match(e.span_id, /^[0-9a-f]{16}$/);
  assert.equal(e.parent_span_id, "b".repeat(16));
  assert.equal(e.attributes["axis.turn"], 1);
  assert.equal(e.attributes["tool.name"], "run");
});

// ---------------------------------------------------------------------------
// SqliteEventSink integration tests (real DB, temp file)
// ---------------------------------------------------------------------------

test("SqliteEventSink: ok() is true for a writable DB", async () => {
  const dir = await mkdtemp(join(tmpdir(), "sqlite-audit-"));
  const dbPath = join(dir, "audit.db");
  try {
    const sink = new SqliteEventSink({ dbPath });
    assert.equal(sink.ok(), true);
    sink.close();
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("SqliteEventSink: events are written to the DB", async () => {
  const dir = await mkdtemp(join(tmpdir(), "sqlite-audit-"));
  const dbPath = join(dir, "audit.db");
  try {
    const sink = new SqliteEventSink({ dbPath });
    const identity = id();
    sink.emit(buildSessionStart(identity));
    sink.emit(
      buildToolCall({
        identity,
        seq: 0,
        argvRedacted: ["bash", "-c", "echo hi"],
        decision: "allow",
        result: { code: 0, durationMs: 7, timedOut: false },
      }),
    );
    sink.emit(buildSessionEnd(identity));
    sink.close();

    // Read back via a fresh DB connection to verify durability.
    const db = new Database(dbPath, { readonly: true });
    const rows = db.prepare("SELECT * FROM events ORDER BY id").all();
    db.close();

    assert.equal(rows.length, 3);
    assert.equal(JSON.parse(rows[0].data).event, "axis.session_start");
    assert.equal(JSON.parse(rows[1].data).event, "axis.toolcall");
    assert.equal(JSON.parse(rows[2].data).event, "axis.session_end");

    // Verify columns populated correctly.
    assert.equal(rows[1].event, "axis.toolcall");
    assert.equal(rows[1].session, "sess-sqlite-1");
    assert.equal(typeof rows[1].time, "number");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("SqliteEventSink: emit degrades to a no-op (ok()=false) on an invalid path", () => {
  // A path whose directory component does not exist can't be opened.
  const sink = new SqliteEventSink({ dbPath: "/nonexistent/path/audit.db" });
  assert.equal(sink.ok(), false);
  // Should not throw; the sink degrades gracefully.
  assert.doesNotThrow(() => {
    sink.emit({ event: "axis.session_start", time: Date.now() / 1000 });
  });
  sink.close();
});

test("SqliteEventSink: event table schema has expected columns", async () => {
  const dir = await mkdtemp(join(tmpdir(), "sqlite-audit-"));
  const dbPath = join(dir, "audit.db");
  try {
    // Instantiate sink to trigger schema creation.
    const sink = new SqliteEventSink({ dbPath });
    sink.close();

    const db = new Database(dbPath, { readonly: true });
    const cols = db
      .prepare("PRAGMA table_info(events)")
      .all()
      .map((r) => r.name);
    db.close();

    for (const col of ["id", "time", "event", "session", "data"]) {
      assert.ok(cols.includes(col), `column ${col} should exist`);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
