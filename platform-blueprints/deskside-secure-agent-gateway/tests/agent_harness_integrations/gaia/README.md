<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side gaia Test: the axis MCP connector driven by **gaia** (a 2nd MCP host) + **SQLite audit DB**

Proves the **same** client-side `axis_mcp_connector` that Claude Code uses also works when the MCP
host is [**gaia**](https://github.com/amd/gaia) (AMD's agent framework) — every gaia-driven tool
call flows through the AXIS sandbox (sole enforcement) → the local SQLite audit DB, which ends up
holding events from **both** a gaia session and a Claude-Code session, demonstrating one connector
serving two hosts.

This is the gaia sibling of [`../claude_code/`](../claude_code/). The
entire control/audit plane is unchanged (same connector, AXIS sandbox, SQLite audit DB). Only the
**MCP host** changes: gaia instead of — and in addition to — Claude Code. No connector code is
modified; it is reused unchanged by path.

```
   gaia (MCP host)                         Claude Code (MCP host)
     │ MCPClient.from_config / Agent          │ .mcp.json -> mcp__axis__run
     │ (gaia.mcp.client.MCPClient)            │
     └──────────────┬─────────────────────────┘
                    ▼
        axis MCP connector (Node, reused from gateway)
                    │ identity -> AXIS sandbox (sole enforcement) -> SQLite audit event
                    ▼
   AXIS sandbox (Landlock+seccomp+netns)              SQLite audit DB
                                                      AUDIT_DB (default artifacts/audit.db)
                                                      events read back with SQL
```

## What it proves

1. **gaia speaks to the connector** — gaia's own MCP client (`gaia.mcp.client.MCPClient`,
   registered from an `mcp_servers.json` carrying the full connector env) connects and lists the
   `run` tool.
2. **gaia deterministic probe (HARD)** — gaia's MCP client invokes `run('echo GAIA_OK && hostname')`
   under session `gaia-probe`; real sandbox output comes back, and the
   `axis.toolcall(decision=allow)` event is **read back out of the SQLite audit DB with SQL**. This
   is model-independent — no LLM is involved, so it cannot be blocked by gaia↔gateway inference
   wiring.
3. **cross-host** — a Claude-Code run-tool call (session `cc-gaia`) lands its own event in the same
   audit DB, and the final check confirms the SQLite DB holds **both** a gaia session and a
   Claude-Code session.
4. **gaia agentic** — a gaia `Agent` whose LLM is **`Qwen3-8B-GGUF` on CPU via the local Lemonade
   server** decides on its own to call the `run` tool (session `gaia-agent`); the event is confirmed
   in the SQLite audit DB. gaia uses its native Lemonade provider (its built-in Claude/OpenAI
   providers don't honour a custom gateway base_url). If Lemonade is unavailable the stage is
   reported **SKIP** (the stage-4 deterministic probe still HARD-proves the gaia↔connector↔SQLite
   integration).

A silent write failure cannot pass: the audit assertions read the event back out of the SQLite DB,
not from an in-memory sink.

## Reuse (no duplication)

- `../../../stack/axis_mcp_connector/` — connector + the connector unit tests (unchanged)
- `../../lib/audit_db.sh` — shared SQLite audit-DB read-back helpers
- `../claude_code/claude_job.sh` — the cross-host Claude-Code launcher (gateway)

## Layout

```
gaia/
  README.md  SETUP.md  RESULTS.md
  run_gaia_integration.sh   end-to-end runner (the main new code)
  gaia_mcp_probe.py         deterministic HARD proof: gaia's MCPClient drives the connector's run
  gaia_agent_query.py       best-effort agentic: a gaia Agent calls the tool via the gateway
  artifacts/                outputs (SUMMARY.txt, audit.db, gaia_*.out, …)
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd tests/agent_harness_integrations/gaia
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
  bash run_gaia_integration.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
