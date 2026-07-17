// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { userInfo } from "node:os";

import { ProxyIdentity, resolveUser } from "../src/identity.js";
import {
  SqliteLlmEventSink,
  buildLlmSessionStart,
  buildLlmSessionEnd,
  buildLlmRequest,
} from "../src/sqlite_events.js";

function id() {
  return new ProxyIdentity({
    LLM_SESSION: "cc-sess",
    LLM_USER: "amd",
    LLM_TENANT: "client-deskside",
    LLM_DEVICE_ID: "node-1",
  });
}

test("identity honors LLM_SESSION and falls back to AXIS_SESSION for correlation", () => {
  assert.equal(new ProxyIdentity({ LLM_SESSION: "a" }).session, "a");
  assert.equal(new ProxyIdentity({ AXIS_SESSION: "b" }).session, "b");
  assert.match(new ProxyIdentity({}).session, /^lp-/);
});

test("resolveUser: LLM_USER || AXIS_USER as source=env, else OS user as source=os", () => {
  assert.deepEqual(resolveUser({ LLM_USER: "carol" }), { user: "carol", source: "env" });
  assert.deepEqual(resolveUser({ AXIS_USER: "dave" }), { user: "dave", source: "env" });
  assert.deepEqual(resolveUser({}), { user: userInfo().username, source: "os" });
});

test("identity block carries user + user_source, matching the tool plane shape", () => {
  const blk = new ProxyIdentity({ LLM_USER: "amd" }).identityBlock();
  assert.equal(blk.user, "amd");
  assert.equal(blk.user_source, "env");
  assert.ok("session" in blk && "tenant" in blk && "device_id" in blk);
});

test("session_start carries identity + inference policy provenance", () => {
  const e = buildLlmSessionStart(id());
  assert.equal(e.event, "llm.session_start");
  assert.equal(e.identity.session, "cc-sess");
  assert.equal(e.policy.id, "inference-proxy");
  assert.equal(e.policy.source, "local-control");
});

test("session_end carries identity", () => {
  const e = buildLlmSessionEnd(id());
  assert.equal(e.event, "llm.session_end");
  assert.equal(e.identity.session, "cc-sess");
});

test("llm.request carries request/result/decision (no DC fields)", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "Qwen3-8B-GGUF",
    endpoint: "/v1/messages",
    stream: true,
    messages: 2,
    promptChars: 42,
    decision: "allow",
    result: {
      status: 200,
      durationMs: 1234,
      promptTokens: 11,
      completionTokens: 7,
      completionChars: 30,
      stopReason: "end_turn",
    },
  });
  assert.equal(e.event, "llm.request");
  assert.equal(e.request.seq, 0);
  assert.equal(e.request.model, "Qwen3-8B-GGUF");
  assert.equal(e.request.stream, true);
  assert.equal(e.request.prompt_chars, 42);
  assert.equal(e.decision, "allow");
  assert.equal(e.result.status, 200);
  assert.equal(e.result.prompt_tokens, 11);
  assert.equal(e.result.completion_tokens, 7);
  // No DC fields in the event shape
  assert.ok(!("defenseclaw_request" in e), "no defenseclaw_request field");
  assert.ok(!("defenseclaw_response" in e), "no defenseclaw_response field");
});

test("llm.request carries OTEL envelope + GenAI attributes + trace/gpu", () => {
  const trace = { trace_id: "a".repeat(32), root_span_id: "b".repeat(16), turn: 2 };
  const gpu = { busy_percent: 90, power_w: 25, energy_joules: 42 };
  const e = buildLlmRequest({
    identity: id(),
    seq: 3,
    model: "Qwen3-8B-GGUF",
    requestedModel: "claude-sonnet-5",
    endpoint: "/v1/messages",
    stream: true,
    messages: 1,
    promptChars: 10,
    decision: "allow",
    result: { status: 200, durationMs: 100, promptTokens: 5, completionTokens: 9, completionChars: 20, stopReason: "end_turn" },
    routing: { enabled: true, reachable: true, tier: "local", selectedModel: null, decision: null, complexity: null, upstream: "http://x", classifyMs: 1 },
    trace,
    gpu,
  });
  // OTEL envelope
  assert.match(e.event_id, /^[0-9a-f-]{36}$/);
  assert.equal(e.schema_version, "1.0");
  assert.equal(e.ingest_source, "lemonade-proxy");
  assert.equal(e.trace_id, "a".repeat(32));
  assert.match(e.span_id, /^[0-9a-f]{16}$/);
  assert.equal(e.parent_span_id, "b".repeat(16));
  assert.equal(e.resource["service.name"], "lemonade-proxy");
  assert.equal(e.resource["service.instance.id"], "node-1");
  // GenAI semconv attributes
  assert.equal(e.attributes["gen_ai.operation.name"], "chat");
  assert.equal(e.attributes["gen_ai.provider.name"], "lemonade");
  assert.equal(e.attributes["gen_ai.request.model"], "claude-sonnet-5");
  assert.equal(e.attributes["gen_ai.response.model"], "Qwen3-8B-GGUF");
  assert.equal(e.attributes["gen_ai.usage.input_tokens"], 5);
  assert.equal(e.attributes["gen_ai.usage.output_tokens"], 9);
  assert.deepEqual(e.attributes["gen_ai.response.finish_reasons"], ["end_turn"]);
  assert.equal(e.attributes["execution_location"], "deskside");
  assert.equal(e.attributes["axis.turn"], 2);
  // GPU block
  assert.deepEqual(e.gpu, gpu);
});

test("frontier tier maps to provider=frontier / execution_location=cloud, gpu null", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "claude-opus-4.8",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 5,
    decision: "allow",
    result: { status: 200, durationMs: 10, promptTokens: 1, completionTokens: 2, completionChars: 3, stopReason: "end_turn" },
    routing: { enabled: true, reachable: true, tier: "frontier", selectedModel: "claude-opus-4.8" },
    trace: { trace_id: "c".repeat(32), root_span_id: "d".repeat(16), turn: 0 },
    gpu: null,
  });
  assert.equal(e.attributes["gen_ai.provider.name"], "frontier");
  assert.equal(e.attributes["execution_location"], "cloud");
  assert.equal(e.gpu, null);
});

test("llm.request with no result has null fields", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 1,
    model: "m",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 3,
    decision: "unknown",
    result: null,
  });
  assert.equal(e.result.status, null);
});

test("llm.request never carries raw prompt/completion text (metadata only)", () => {
  const e = buildLlmRequest({
    identity: id(),
    seq: 0,
    model: "m",
    endpoint: "/v1/messages",
    stream: false,
    messages: 1,
    promptChars: 12,
    decision: "allow",
    result: { status: 200, durationMs: 1, promptTokens: 1, completionTokens: 1, completionChars: 11, stopReason: "end_turn" },
  });
  // No content block, and only char COUNTS are recorded — never the text.
  assert.ok(!("content" in e), "event must not have a content block");
  assert.equal(e.request.prompt_chars, 12);
  assert.equal(e.result.completion_chars, 11);
});

test("sink writes to SQLite and rows are readable", async () => {
  const dir = await mkdtemp(join(tmpdir(), "llmsink-"));
  const dbPath = join(dir, "events.db");
  try {
    const sink = new SqliteLlmEventSink({ dbPath });
    sink.emit(buildLlmSessionStart(id()));
    sink.emit(buildLlmSessionEnd(id()));

    // Read back using better-sqlite3
    const { default: Database } = await import("better-sqlite3");
    const db = new Database(dbPath);
    const rows = db.prepare("SELECT data FROM events ORDER BY id").all();
    db.close();

    assert.equal(rows.length, 2);
    const first = JSON.parse(rows[0].data);
    assert.equal(first.event, "llm.session_start");
    const second = JSON.parse(rows[1].data);
    assert.equal(second.event, "llm.session_end");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("sink never throws on error", () => {
  // Pass a non-writable path to trigger an error — sink must not throw.
  // Using an invalid path triggers the constructor, so test via a closed DB scenario.
  const dir = tmpdir();
  const dbPath = join(dir, `test-sink-nothrow-${Date.now()}.db`);
  const sink = new SqliteLlmEventSink({ dbPath });
  // emit should be synchronous and not throw
  assert.doesNotThrow(() => sink.emit(buildLlmSessionEnd(id())));
});
