// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Scripted MCP client for the client-side connector. Connects to server.js over
// stdio and invokes the `run` tool exactly as Claude Code would if the model
// emitted the tool call. This validates the full control plane (MCP transport
// -> tool registration -> DefenseClaw admission -> AXIS exec -> Splunk event)
// independently of whatever model Lemonade is serving.
//
// Usage: node mcp_probe.mjs <server.js path> <command>
// Inherits AXIS_BIN / AXIS_POLICY / DEFENSECLAW_* / SPLUNK_* / AXIS_SESSION env.
// Exit 0 on success, 1 on tool/transport failure. Prints the tool output text
// (or the [blocked ...] note) to stdout.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const [serverPath, command] = process.argv.slice(2);
if (!serverPath || !command) {
  console.error("usage: node mcp_probe.mjs <server.js> <command>");
  process.exit(2);
}

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [serverPath],
  env: process.env,
});
const client = new Client({ name: "mcp-probe", version: "0.1.0" });
await client.connect(transport);

const tools = await client.listTools();
const names = tools.tools.map((t) => t.name);
if (!names.includes("run")) {
  console.error("FAIL: server did not expose a `run` tool; got:", names);
  process.exit(1);
}

const res = await client.callTool({ name: "run", arguments: { command } });
const text = (res.content || []).map((c) => c.text || "").join("\n");
if (res.isError) {
  console.log("[isError] " + text);
} else {
  console.log(text);
}

await client.close();
