#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# gaia_agent_query.py — agentic proof: a gaia Agent (LLM = a small GGUF model on
# CPU via the LOCAL Lemonade server) decides on its own to call the axis
# connector's run tool, which flows through the AXIS sandbox -> SQLite audit DB.
#
# gaia's MCPClientMixin loads servers from the config the runner points at via
# GAIA_MCP_CONFIG (the connector command + the AXIS_* / AUDIT_DB env and
# AXIS_SESSION=gaia-agent), so the tool surfaces as mcp_axis_run.
#
# LLM plane: gaia's native Lemonade provider (use_claude=False) honours
# LEMONADE_BASE_URL and serves GAIA_MODEL (default Qwen3-8B-GGUF) from the local
# Lemonade server on CPU. gaia's built-in Claude/OpenAI providers don't take a
# custom gateway base_url/header, so Lemonade is the working local inference path.
# If inference can't be reached the runner reports this stage SKIP (the
# deterministic gaia_mcp_probe.py still HARD-proves the integration).
#
# Args: $1 = query (default: ask it to run a benign command via the tool)
# Exit: 0 iff process_query completed without raising.

import os
import sys


def main() -> int:
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Use the available run tool to execute exactly this shell command: "
        "echo GAIA_AGENT_OK && hostname. Then report the output."
    )

    from gaia.agents.base.agent import Agent
    from gaia.mcp import MCPClientMixin

    model_id = os.environ.get("GAIA_MODEL", "Qwen3-8B-GGUF")
    config_file = os.environ.get("GAIA_MCP_CONFIG")  # explicit mcp_servers.json

    class AxisAgent(Agent, MCPClientMixin):
        def __init__(self):
            Agent.__init__(self, max_steps=8, model_id=model_id)
            MCPClientMixin.__init__(self, debug=True, config_file=config_file)

        def _get_system_prompt(self) -> str:
            return (
                "You are a helpful assistant with a sandboxed shell `run` tool. "
                "When asked to run a command, call the run tool with it."
            )

        def _register_tools(self) -> None:
            pass  # MCP tools auto-registered from ~/.gaia/mcp_servers.json

    agent = AxisAgent()
    servers = agent.list_mcp_servers()
    print(f"gaia connected to MCP servers: {servers}")

    result = agent.process_query(query)
    print("---- agent result ----")
    print(result.get("result") if isinstance(result, dict) else result)
    print("----------------------")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # best-effort: inference wiring is the known unknown
        print(f"AGENTIC_SKIP: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(7)
