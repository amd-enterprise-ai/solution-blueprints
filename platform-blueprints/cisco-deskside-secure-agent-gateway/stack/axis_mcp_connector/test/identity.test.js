// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { userInfo } from "node:os";

import { makeSessionId, SessionIdentity, resolveUser } from "../src/identity.js";

test("makeSessionId honors injected session", () => {
  assert.equal(makeSessionId("my-sess"), "my-sess");
  assert.equal(makeSessionId("  spaced  "), "spaced");
});

test("makeSessionId mints a cc-uuid when none given", () => {
  const a = makeSessionId("");
  const b = makeSessionId(undefined);
  assert.match(a, /^cc-[0-9a-f-]{36}$/);
  assert.notEqual(a, b);
});

test("identity block carries session/user/user_source/tenant/device with defaults", () => {
  const id = new SessionIdentity({});
  const blk = id.identityBlock();
  assert.equal(blk.session, id.session);
  // No AXIS_USER: default resolves to the OS login user, source "os"
  // (falls back to "unknown"/"unknown" only if the OS user can't be read).
  assert.ok(blk.user);
  assert.ok(["os", "unknown"].includes(blk.user_source));
  assert.equal(blk.tenant, "client-deskside");
  assert.ok(blk.device_id);
});

test("resolveUser: AXIS_USER wins as source=env", () => {
  assert.deepEqual(resolveUser({ AXIS_USER: "alice" }), { user: "alice", source: "env" });
  assert.deepEqual(resolveUser({ AXIS_USER: "  bob  " }), { user: "bob", source: "env" });
});

test("resolveUser: no env falls back to the OS login user as source=os", () => {
  const os = userInfo().username;
  assert.deepEqual(resolveUser({}), { user: os, source: "os" });
});

test("identity reads env overrides", () => {
  const id = new SessionIdentity({
    AXIS_SESSION: "sess-1",
    AXIS_USER: "alice",
    AXIS_TENANT: "acme",
    AXIS_DEVICE_ID: "dev-9",
    AXIS_POLICY_SOURCE: "cloud-control",
    AXIS_POLICY_ID: "strict",
  });
  assert.equal(id.session, "sess-1");
  assert.equal(id.user, "alice");
  assert.equal(id.userSource, "env");
  assert.equal(id.identityBlock().user_source, "env");
  assert.equal(id.tenant, "acme");
  assert.equal(id.deviceId, "dev-9");
  assert.equal(id.policySource, "cloud-control");
  assert.equal(id.policyId, "strict");
});

test("lifecycle: start once, seq increments, end once", () => {
  const id = new SessionIdentity({});
  assert.equal(id.start(), true, "first start true");
  assert.equal(id.start(), false, "second start false");
  assert.equal(id.nextSeq(), 0);
  assert.equal(id.nextSeq(), 1);
  assert.equal(id.nextSeq(), 2);
  assert.equal(id.end(), true, "first end true");
  assert.equal(id.end(), false, "second end false");
});

test("end before start returns false", () => {
  const id = new SessionIdentity({});
  assert.equal(id.end(), false);
});
