// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { makeSessionId, SessionIdentity } from "../src/identity.js";

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

test("identity block carries session/user/tenant/device with defaults", () => {
  const id = new SessionIdentity({});
  const blk = id.identityBlock();
  assert.equal(blk.session, id.session);
  assert.equal(blk.user, "unknown");
  assert.equal(blk.tenant, "client-deskside");
  assert.ok(blk.device_id);
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
