#!/usr/bin/env node
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Client-side MCP stdio server for Claude Code (AMD-only deployment).
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
//   2. axis       — run `axis run --policy <p> -- bash -c <cmd>` under the AXIS
//                   sandbox (Landlock + seccomp + netns), capturing real
//                   stdout/stderr/exit. AXIS is the sole enforcement layer.
//   3. sqlite     — build an axis.toolcall event (identity + policy +
//                   command + decision + result) -> SQLite sink.
//   4. return the command output to Claude Code.
// On shutdown (stdin close / SIGTERM) emit axis.session_end.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { SessionIdentity } from "./identity.js";
import { TraceReader } from "./trace.js";
import { runInSandbox, formatToolResult, redactCommand } from "./axis.js";
import {
  SqliteEventSink,
  buildSessionStart,
  buildSessionEnd,
  buildToolCall,
} from "./sqlite_events.js";

const cfg = {
  axisBin: process.env.AXIS_BIN || "axis",
  axisPolicy: process.env.AXIS_POLICY || "/etc/axis/coding-agent.yaml",
  auditDb: process.env.AUDIT_DB || "./audit.db",
};

const identity = new SessionIdentity(process.env);
// Reads the per-turn trace the inference proxy writes to the shared statefile so
// tool calls carry the same trace_id as the turn's LLM calls.
const traceReader = new TraceReader(identity.session, process.env);
const sink = new SqliteEventSink({ dbPath: cfg.auditDb });

const log = (...a) => console.error("[axis-mcp]", ...a);

async function ensureSessionStarted() {
  if (identity.start()) {
    try {
      sink.emit(buildSessionStart(identity));
    } catch (e) {
      log("session_start emit failed:", e.message || e);
    }
  }
}

const server = new McpServer({ name: "axis", version: "0.1.0" });

server.tool(
  "run",
  "Run a shell command on the local machine inside an AXIS sandbox " +
    "(Landlock + seccomp + netns). Returns the command's stdout/stderr and " +
    "exit code. Every call is recorded as an audit event in the local SQLite " +
    "database.",
  { command: z.string().describe("The shell command to execute.") },
  async ({ command }) => {
    await ensureSessionStarted();
    const seq = identity.nextSeq();
    const trace = traceReader.current();
    const argvRedacted = ["bash", "-c", redactCommand(command)];

    // 2. AXIS execution — the sole enforcement layer (Landlock/seccomp/netns).
    const result = await runInSandbox({
      axisBin: cfg.axisBin,
      policy: cfg.axisPolicy,
      command,
    });

    // exit 0 = allow; non-zero = "error". A non-zero exit may be an ordinary
    // command failure OR a Landlock/seccomp denial — the connector cannot tell
    // them apart from the exit code, so it does NOT claim "deny".
    const decision = result.code === 0 ? "allow" : "error";

    // 3. SQLite audit event (redacted argv only — never the raw command).
    try {
      sink.emit(
        buildToolCall({
          identity,
          seq,
          argvRedacted,
          decision,
          result,
          trace,
        }),
      );
    } catch (e) {
      log("toolcall emit failed:", e.message || e);
    }

    log(
      `run seq=${seq} session=${identity.session} trace=${trace.trace_id}: ${command} -> exit ${result.code} decision=${decision}`,
    );
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
      audit_db: cfg.auditDb,
    };
    return { content: [{ type: "text", text: JSON.stringify(body, null, 2) }] };
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log(
    `connected; session=${identity.session} axis=${cfg.axisBin} policy=${cfg.axisPolicy} ` +
      `audit_db=${cfg.auditDb}`,
  );

  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (identity.end()) {
      try {
        sink.emit(buildSessionEnd(identity));
      } catch (e) {
        log("session_end emit failed:", e.message || e);
      }
    }
    sink.close();
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
