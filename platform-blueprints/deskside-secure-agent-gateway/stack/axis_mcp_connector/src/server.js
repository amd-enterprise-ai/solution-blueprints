#!/usr/bin/env node
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Client-side MCP stdio server for Claude Code.
//
// Two-plane model: Claude Code gets *inference* from a local Lemonade server,
// and routes every side-effecting *tool call* through this connector. The
// harness is launched with Bash/Read/Write/Edit disallowed so the only way for
// the agent to act on the machine is the `run` tool here — which gives complete
// audit coverage.
//
// Per `run` call the pipeline is:
//   1. identity   — ensure the session started (emit axis.session_start once);
//                   assign a seq for this call.
//   2. defenseclaw — POST the tool_call to the gateway; get allow/block.
//                    In action mode a HIGH/CRITICAL block skips execution.
//   3. axis       — if allowed, run `axis run --policy <p> -- bash -c <cmd>`,
//                   capturing real stdout/stderr/exit.
//   4. defenseclaw — optionally inspect the tool_result (observe lane).
//   5. splunk     — build an axis.toolcall HEC-shaped event (identity + policy +
//                   command + decision + result + findings) -> local sink.
//   6. return the command output to Claude Code.
// On shutdown (stdin close / SIGTERM) emit axis.session_end.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { SessionIdentity } from "./identity.js";
import { TraceReader } from "./trace.js";
import { runInSandbox, formatToolResult, redactCommand } from "./axis.js";
import { DefenseClawClient } from "./defenseclaw.js";
import {
  SplunkEventSink,
  buildSessionStart,
  buildSessionEnd,
  buildToolCall,
} from "./splunk_events.js";

const cfg = {
  axisBin: process.env.AXIS_BIN || "axis",
  axisPolicy: process.env.AXIS_POLICY || "/etc/axis/coding-agent.yaml",
  defenseclawUrl: process.env.DEFENSECLAW_URL || "http://127.0.0.1:18970",
  defenseclawToken: process.env.DEFENSECLAW_GATEWAY_TOKEN || "",
  defenseclawMode: process.env.DEFENSECLAW_MODE || "action",
  defenseclawFailOpen: process.env.DEFENSECLAW_FAIL_OPEN === "1",
  inspectResult: process.env.DEFENSECLAW_INSPECT_RESULT === "1",
  splunkSink: process.env.SPLUNK_SINK || null,
  splunkHecUrl: process.env.SPLUNK_HEC_URL || null,
  splunkHecToken: process.env.SPLUNK_HEC_TOKEN || "fake-token",
  // Fail-closed audit: when set, a tool call is REFUSED if the audit sink is
  // unreachable, so no command ever runs without an audit trail. Default off
  // preserves the prior best-effort behaviour (existing suites unaffected).
  auditRequired: process.env.AUDIT_REQUIRED === "1",
};

const identity = new SessionIdentity(process.env);
// Reads the per-turn trace the inference proxy writes to the shared statefile so
// tool calls carry the same trace_id as the turn's LLM calls.
const traceReader = new TraceReader(identity.session, process.env);
const guard = new DefenseClawClient({
  baseUrl: cfg.defenseclawUrl,
  token: cfg.defenseclawToken,
  mode: cfg.defenseclawMode,
  failOpen: cfg.defenseclawFailOpen,
});
const sink = new SplunkEventSink({
  sinkPath: cfg.splunkSink,
  hecUrl: cfg.splunkHecUrl,
  hecToken: cfg.splunkHecToken,
});

const log = (...a) => console.error("[axis-mcp]", ...a);

async function ensureSessionStarted() {
  if (identity.start()) {
    await sink.emit(buildSessionStart(identity)).catch((e) => log("session_start emit failed:", e.message || e));
  }
}

const server = new McpServer({ name: "axis", version: "0.1.0" });

server.tool(
  "run",
  "Run a shell command on the local machine inside an AXIS sandbox. The call " +
    "is first admitted by the Cisco DefenseClaw gateway (policy/guardrails); if " +
    "allowed it executes under AXIS isolation. Returns the command's " +
    "stdout/stderr and exit code. Every call is recorded as a Splunk-shaped " +
    "audit event.",
  { command: z.string().describe("The shell command to execute.") },
  async ({ command }) => {
    await ensureSessionStarted();
    const seq = identity.nextSeq();
    const trace = traceReader.current();
    const argv = ["bash", "-c", command];
    const argvRedacted = ["bash", "-c", redactCommand(command)];

    // 2. DefenseClaw admission.
    const verdict = await guard.admitToolCall({
      session: identity.session,
      tool: "run",
      argv,
      cwd: process.cwd(),
    });

    if (verdict.decision === "block") {
      await sink
        .emit(
          buildToolCall({
            identity,
            seq,
            argv,
            argvRedacted,
            decision: "block",
            result: null,
            defenseclaw: verdict,
            trace,
          }),
        )
        .catch((e) => log("toolcall emit failed:", e.message || e));
      log(`run seq=${seq} BLOCKED by DefenseClaw sev=${verdict.severity} findings=${verdict.findings.join(",")}`);
      const note =
        `[blocked by DefenseClaw] severity=${verdict.severity}` +
        (verdict.findings.length ? ` findings: ${verdict.findings.join("; ")}` : "") +
        (verdict.reason ? `\n${verdict.reason}` : "");
      return { content: [{ type: "text", text: note }], isError: true };
    }

    // 2b. Fail-closed audit gate: refuse to execute if the audit sink can't
    //     accept the record, so there is never an unaudited execution.
    if (cfg.auditRequired && !(await sink.reachable())) {
      await sink.emitLocal(
        buildToolCall({
          identity,
          seq,
          argv,
          argvRedacted,
          decision: "block",
          result: null,
          defenseclaw: { ...verdict, reason: "audit-sink-unreachable" },
          trace,
        }),
      );
      log(`run seq=${seq} REFUSED: audit sink unreachable (fail-closed)`);
      return {
        content: [
          {
            type: "text",
            text: "[refused] audit sink unreachable — refusing to execute (fail-closed audit)",
          },
        ],
        isError: true,
      };
    }

    // 3. AXIS execution.
    const result = await runInSandbox({
      axisBin: cfg.axisBin,
      policy: cfg.axisPolicy,
      command,
    });

    // 4. Optional tool_result inspection (observe).
    if (cfg.inspectResult) {
      await guard.inspectToolResult({
        session: identity.session,
        tool: "run",
        content: `${result.stdout}\n${result.stderr}`.slice(0, 8192),
      });
    }

    // A non-zero exit after an allow is treated as a sandbox denial for audit.
    const decision = !verdict.reachable && !cfg.defenseclawFailOpen
      ? "unknown"
      : result.code === 0
        ? "allow"
        : "deny";

    // 5. Splunk audit event.
    await sink
      .emit(
        buildToolCall({
          identity,
          seq,
          argv,
          argvRedacted,
          decision,
          result,
          defenseclaw: verdict,
          trace,
        }),
      )
      .catch((e) => log("toolcall emit failed:", e.message || e));

    log(`run seq=${seq} session=${identity.session} trace=${trace.trace_id}: ${command} -> exit ${result.code} decision=${decision}`);
    return { content: [{ type: "text", text: formatToolResult(result) }] };
  },
);

server.tool(
  "session_info",
  "Report this agent session's identity (session id, user, tenant, device) and " +
    "the number of tool calls recorded so far.",
  {},
  async () => {
    const body = {
      ...identity.identityBlock(),
      policy: { id: identity.policyId, source: identity.policySource },
      tool_calls: identity.seq,
      defenseclaw: { url: cfg.defenseclawUrl, mode: cfg.defenseclawMode },
      splunk_sink: cfg.splunkSink,
    };
    return { content: [{ type: "text", text: JSON.stringify(body, null, 2) }] };
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log(
    `connected; session=${identity.session} axis=${cfg.axisBin} policy=${cfg.axisPolicy} ` +
      `defenseclaw=${cfg.defenseclawUrl}(${cfg.defenseclawMode}) sink=${cfg.splunkSink}`,
  );

  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (identity.end()) {
      await sink.emit(buildSessionEnd(identity)).catch((e) => log("session_end emit failed:", e.message || e));
    }
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  process.stdin.on("close", shutdown);
}

main().catch((e) => {
  log("fatal:", e);
  process.exit(1);
});
