// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Cross-plane session correlation contract.
//
// The tool plane (axis_mcp_connector) and the inference plane (lemonade_proxy)
// run as separate processes and emit into the same SQLite audit DB. They only
// correlate if both stamp the SAME identity.session. The agreed seam is a single
// AXIS_SESSION exported by whatever launches the agent, inherited by both planes,
// with LLM_SESSION left unset so the proxy falls back to AXIS_SESSION.
//
// This test locks that contract at the code level so a future rename of the env
// var (or a change to the fallback order) fails fast, independent of any node run.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ProxyIdentity } from "../src/identity.js";
import { TraceState } from "../src/trace.js";
import { SessionIdentity } from "../../axis_mcp_connector/src/identity.js";
import { TraceReader } from "../../axis_mcp_connector/src/trace.js";

test("both planes share identity.session when a single AXIS_SESSION is injected (LLM_SESSION unset)", () => {
  const env = {
    AXIS_SESSION: "cc-unified-1",
    AXIS_USER: "amd",
    AXIS_TENANT: "client-deskside",
    AXIS_DEVICE_ID: "node-1",
  };
  const tool = new SessionIdentity(env);
  const infer = new ProxyIdentity(env);

  assert.equal(tool.session, "cc-unified-1");
  assert.equal(infer.session, "cc-unified-1");
  // The whole identity block (the fields both planes ship) must match, so a
  // query on any of them returns both planes for one logical session.
  assert.deepEqual(infer.identityBlock(), tool.identityBlock());
});

test("a per-plane LLM_SESSION override breaks correlation (documents the footgun)", () => {
  const env = { AXIS_SESSION: "cc-unified-2", LLM_SESSION: "lp-divergent" };
  const tool = new SessionIdentity(env);
  const infer = new ProxyIdentity(env);

  assert.equal(tool.session, "cc-unified-2");
  assert.equal(infer.session, "lp-divergent");
  assert.notEqual(infer.session, tool.session);
});

test("with nothing injected each plane mints its own prefixed id (no accidental correlation)", () => {
  const tool = new SessionIdentity({});
  const infer = new ProxyIdentity({});
  assert.match(tool.session, /^cc-/);
  assert.match(infer.session, /^lp-/);
  assert.notEqual(infer.session, tool.session);
});

test("both planes share the per-turn trace_id via the statefile (proxy writes, connector reads)", async () => {
  const dir = await mkdtemp(join(tmpdir(), "xplane-trace-"));
  try {
    // One AXIS_TRACE_STATE exported to both planes, like AXIS_SESSION.
    const env = { AXIS_SESSION: "cc-unified-3", AXIS_TRACE_STATE: join(dir, "trace.json") };
    // Inference plane is the authority: it mints the turn's trace.
    const proxyTrace = new TraceState(new ProxyIdentity(env).session, env);
    const turn0 = proxyTrace.startTurn();
    // Tool plane reads the SAME trace for its tool calls in that turn.
    const connReader = new TraceReader(new SessionIdentity(env).session, env);
    assert.equal(connReader.current().trace_id, turn0.trace_id);
    assert.equal(connReader.current().root_span_id, turn0.root_span_id);
    // A new user turn advances the trace; the connector picks it up.
    const turn1 = proxyTrace.startTurn();
    assert.notEqual(turn1.trace_id, turn0.trace_id);
    assert.equal(connReader.current().trace_id, turn1.trace_id);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
