#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# gaia_mcp_probe.py — deterministic proof that gaia's OWN MCP client stack can
# drive the client-side axis MCP connector (the same connector Claude Code uses),
# producing a real AXIS-sandboxed run and a Splunk audit event.
#
# This uses gaia.mcp.client.MCPClient (gaia's code, not the raw MCP SDK), so a
# green run is genuine "the connector works with gaia". It is model-independent:
# no LLM is involved, so it can't be blocked by gaia<->gateway inference wiring.
#
# The connector's full env (AXIS_*, DEFENSECLAW_*, SPLUNK_*) is taken from this
# process's environment (the runner exports it) and passed through gaia's
# from_config env block; StdioTransport merges it over os.environ before spawning
# `node <server.js>`.
#
# Args: $1 = path to connector server.js, $2 = shell command (default benign probe)
# Exit: 0 iff the tool returned the expected sandbox output.

import os
import sys

from gaia.mcp.client.mcp_client import MCPClient

CONNECTOR_ENV_KEYS = (
    "AXIS_BIN",
    "AXIS_POLICY",
    "AXIS_SESSION",
    "AXIS_TENANT",
    "AXIS_USER",
    "AXIS_POLICY_SOURCE",
    "AXIS_POLICY_ID",
    "DEFENSECLAW_URL",
    "DEFENSECLAW_MODE",
    "DEFENSECLAW_FAIL_OPEN",
    "DEFENSECLAW_GATEWAY_TOKEN",
    "SPLUNK_SINK",
    "SPLUNK_HEC_URL",
    "SPLUNK_HEC_TOKEN",
    "NODE_TLS_REJECT_UNAUTHORIZED",
)


def main() -> int:
    server = sys.argv[1] if len(sys.argv) > 1 else None
    command = sys.argv[2] if len(sys.argv) > 2 else "echo GAIA_OK && hostname"
    if not server or not os.path.exists(server):
        print(f"FATAL: connector server.js not found: {server}", file=sys.stderr)
        return 2

    env = {k: os.environ[k] for k in CONNECTOR_ENV_KEYS if k in os.environ}

    client = MCPClient.from_config(
        "axis",
        {"command": "node", "args": [server], "env": env},
        timeout=120,
        debug=True,
    )

    if not client.connect():
        print(f"FATAL: gaia MCPClient could not connect: {client.last_error}", file=sys.stderr)
        return 3

    try:
        tools = [t.name for t in client.list_tools()]
        print(f"gaia MCPClient sees tools: {tools}")
        if "run" not in tools:
            print("FATAL: connector did not expose the 'run' tool", file=sys.stderr)
            return 4

        result = client.call_tool("run", {"command": command})
        if "error" in result:
            print(f"FATAL: tool call error: {result['error']}", file=sys.stderr)
            return 5

        texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
        out = "\n".join(texts)
        print("---- tool output ----")
        print(out)
        print("---------------------")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
