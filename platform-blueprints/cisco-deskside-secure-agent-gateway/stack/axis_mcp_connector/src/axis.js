// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// AXIS sandbox layer for the client-side connector.
//
// AXIS is an in-process sandbox (seccomp + landlock + netns) applied as an argv
// prefix: `axis run --policy <p> -- bash -c "<cmd>"`. It is the *enforcement*
// plane — it actually isolates and, via landlock/seccomp, can make a forbidden
// action fail with a non-zero exit. DefenseClaw is the separate *policy/verdict*
// plane that decides whether we even hand the command to AXIS.
//
// Ported from rocm-cpu-2010/mcp_connector/src/lib.js (buildAxisArgv /
// runInSandbox / stripAxisLogs / formatToolResult), kept dependency-free so the
// unit tests can inject a fake execFile.

import { execFile } from "node:child_process";

/** Userspace resource caps applied inside the sandbox shell via `ulimit`, for
 *  environments where AXIS's cgroups-based process limits can't be enforced
 *  (e.g. an unprivileged Strix Halo box with no writable cgroups v2). Opt-in via
 *  env so privileged nodes that rely on the policy's own limits are unaffected:
 *    AXIS_ULIMIT_NPROC  -> ulimit -u  (max user processes; caps fork bombs)
 *    AXIS_ULIMIT_AS_KB  -> ulimit -v  (max virtual memory KB; caps memory bombs)
 *  Prefer NPROC: `ulimit -v` caps *virtual* address space, which can break
 *  legit runtimes that reserve large VA regardless of real usage (Go, the JVM,
 *  ASan) — only set AS_KB when you know the workload tolerates it.
 */
export function ulimitPrefix(env = process.env) {
  const parts = [];
  const nproc = env.AXIS_ULIMIT_NPROC;
  const asKb = env.AXIS_ULIMIT_AS_KB;
  if (nproc && /^\d+$/.test(nproc)) parts.push(`ulimit -u ${nproc}`);
  if (asKb && /^\d+$/.test(asKb)) parts.push(`ulimit -v ${asKb}`);
  return parts.length ? parts.join("; ") + "; " : "";
}

/** Build the argv that runs `command` inside an AXIS sandbox. Non-login
 *  `bash -c` (not `-lc`) so the sandbox doesn't trip on profile scripts the
 *  landlock policy forbids. */
export function buildAxisArgv({ axisBin, policy, command, env }) {
  const wrapped = ulimitPrefix(env) + command;
  return [axisBin, "run", "--policy", policy, "--", "bash", "-c", wrapped];
}

/** Run `command` inside AXIS, capturing stdout/stderr/exit. `execFileImpl` is
 *  injectable for tests; defaults to node's execFile. Both streams are run
 *  through stripAxisLogs to leave only the command's real output. */
export function runInSandbox(
  { axisBin, policy, command, cwd, timeoutMs = 120_000 },
  execFileImpl = execFile,
) {
  const [bin, ...args] = buildAxisArgv({ axisBin, policy, command });
  const startedAt = Date.now();
  return new Promise((resolve) => {
    execFileImpl(
      bin,
      args,
      { cwd: cwd || process.cwd(), timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024 },
      (err, stdout, stderr) => {
        resolve({
          code: err && typeof err.code === "number" ? err.code : err ? 1 : 0,
          stdout: stripAxisLogs(stdout || ""),
          stderr: stripAxisLogs(stderr || ""),
          timedOut: Boolean(err && err.killed),
          durationMs: Date.now() - startedAt,
        });
      },
    );
  });
}

/** Drop AXIS's own structured log lines (landlock/seccomp/sandbox banners,
 *  proxy/netns tracing, bashrc-denied noise) so the tool result shows the
 *  command's real output. ANSI codes are stripped first so the tracing regex
 *  matches. */
export function stripAxisLogs(stderr) {
  // eslint-disable-next-line no-control-regex
  const noAnsi = stderr.replace(/\x1B\[[0-9;]*m/g, "");
  return noAnsi
    .split("\n")
    .filter(
      (l) =>
        !/axis_sandbox::|axis_proxy::/.test(l) &&
        !/^AXIS:/.test(l) &&
        !/sandbox will run without network isolation/.test(l) &&
        !/bash: .*\.bashrc: Permission denied/.test(l),
    )
    .join("\n")
    .trim();
}

/** Format a sandbox result into the text returned to the agent. */
export function formatToolResult({ code, stdout, stderr, timedOut }) {
  const parts = [];
  if (stdout) parts.push(stdout.trimEnd());
  if (stderr) parts.push(`[stderr]\n${stderr.trimEnd()}`);
  if (timedOut) parts.push("[command timed out]");
  parts.push(`[exit ${code}]`);
  return parts.join("\n");
}

/** Redact obvious secret-bearing argv for the audit record. The path the agent
 *  reached for is kept (audit needs it); only inline secret *values* are
 *  masked, so the secret reach stays visible in the audit record but the secret
 *  content is not. */
export function redactCommand(command) {
  return command
    .replace(/(--?(?:password|token|secret|api[-_]?key)[=\s]+)(\S+)/gi, "$1<redacted>")
    .replace(/(AWS_SECRET_ACCESS_KEY=)(\S+)/g, "$1<redacted>");
}
