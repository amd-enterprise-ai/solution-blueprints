// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildAxisArgv,
  ulimitPrefix,
  runInSandbox,
  stripAxisLogs,
  formatToolResult,
  redactCommand,
} from "../src/axis.js";

test("buildAxisArgv wraps command in axis run + bash -c", () => {
  // env: {} keeps this hermetic — no ambient AXIS_ULIMIT_* prefix.
  const argv = buildAxisArgv({ axisBin: "axis", policy: "/p.yaml", command: "echo hi", env: {} });
  assert.deepEqual(argv, ["axis", "run", "--policy", "/p.yaml", "--", "bash", "-c", "echo hi"]);
});

test("ulimitPrefix is empty without env, and caps when AXIS_ULIMIT_* set", () => {
  assert.equal(ulimitPrefix({}), "");
  assert.equal(ulimitPrefix({ AXIS_ULIMIT_NPROC: "512" }), "ulimit -u 512; ");
  assert.equal(
    ulimitPrefix({ AXIS_ULIMIT_NPROC: "512", AXIS_ULIMIT_AS_KB: "1048576" }),
    "ulimit -u 512; ulimit -v 1048576; ",
  );
  assert.equal(ulimitPrefix({ AXIS_ULIMIT_NPROC: "bad" }), ""); // non-numeric ignored
});

test("buildAxisArgv applies the ulimit cap when env requests it", () => {
  const argv = buildAxisArgv({
    axisBin: "axis", policy: "/p.yaml", command: "echo hi",
    env: { AXIS_ULIMIT_NPROC: "512" },
  });
  assert.deepEqual(argv, ["axis", "run", "--policy", "/p.yaml", "--", "bash", "-c", "ulimit -u 512; echo hi"]);
});

test("stripAxisLogs removes ANSI + sandbox banners, keeps real output", () => {
  const raw =
    "\x1B[32mhello\x1B[0m\n" +
    "axis_sandbox::landlock applied\n" +
    "AXIS: starting\n" +
    "sandbox will run without network isolation\n" +
    "bash: /home/x/.bashrc: Permission denied\n" +
    "real-line";
  const out = stripAxisLogs(raw);
  assert.equal(out, "hello\nreal-line");
});

test("formatToolResult includes stdout, stderr, exit", () => {
  const txt = formatToolResult({ code: 3, stdout: "out", stderr: "err", timedOut: false });
  assert.match(txt, /out/);
  assert.match(txt, /\[stderr\]\nerr/);
  assert.match(txt, /\[exit 3\]/);
});

test("formatToolResult flags timeout", () => {
  const txt = formatToolResult({ code: 1, stdout: "", stderr: "", timedOut: true });
  assert.match(txt, /\[command timed out\]/);
});

test("redactCommand masks inline secrets, keeps the rest", () => {
  assert.equal(redactCommand("curl --token abc123 http://x"), "curl --token <redacted> http://x");
  assert.equal(redactCommand("cat /etc/hostname"), "cat /etc/hostname");
  assert.match(redactCommand("AWS_SECRET_ACCESS_KEY=zzz aws s3 ls"), /AWS_SECRET_ACCESS_KEY=<redacted>/);
});

test("runInSandbox normalizes exit code and strips logs via injected execFile", async () => {
  const fakeExec = (bin, args, opts, cb) => {
    assert.equal(bin, "axis");
    assert.deepEqual(args.slice(0, 4), ["run", "--policy", "/p.yaml", "--"]);
    cb(null, "axis_sandbox::noise\nclean-out", "");
  };
  const res = await runInSandbox(
    { axisBin: "axis", policy: "/p.yaml", command: "echo x" },
    fakeExec,
  );
  assert.equal(res.code, 0);
  assert.equal(res.stdout, "clean-out");
  assert.equal(typeof res.durationMs, "number");
});

test("runInSandbox maps error.code to exit and detects timeout", async () => {
  const fakeExec = (bin, args, opts, cb) => {
    const err = new Error("nope");
    err.code = 7;
    err.killed = true;
    cb(err, "", "boom");
  };
  const res = await runInSandbox(
    { axisBin: "axis", policy: "/p.yaml", command: "false" },
    fakeExec,
  );
  assert.equal(res.code, 7);
  assert.equal(res.timedOut, true);
});
