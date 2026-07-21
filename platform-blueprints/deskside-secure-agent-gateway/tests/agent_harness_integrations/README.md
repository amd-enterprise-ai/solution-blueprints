<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agent harness integrations

End-to-end demos of the [gateway](../../stack/) governing **real agent harnesses**
on real tasks. Each proves the *same* `axis_mcp_connector` — every tool call flows
through the AXIS sandbox (sole enforcement) → a SQLite audit event — while the MCP
*host* changes.

| Demo | Host | What it shows |
|------|------|---------------|
| [`claude_code/`](./claude_code/) | Claude Code | Solves the real SWE-bench issue `pallets__flask-5014` under full governance; every tool call verified in the SQLite audit DB. |
| [`gaia/`](./gaia/) | [gaia](https://github.com/amd/gaia) | The same connector driven by a *second* MCP host — one connector, two hosts, both landing in one SQLite audit DB. |

Each demo is self-contained: see its `README.md` for what it proves and the
copy-paste "Setup & run" section. The two headline quick-starts (swebench + gaia) are in the
[top-level README](../../README.md).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
