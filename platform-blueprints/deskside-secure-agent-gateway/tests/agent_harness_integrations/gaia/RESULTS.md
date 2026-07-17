<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side gaia test

Status: ✅ **PASS** — verified on a Strix Halo deskside, 2026-07-01T06:26:10Z.

```
gaia LLM (agentic) = Qwen3-8B-GGUF on CPU via local Lemonade :13305
control/audit: gateway=https://<llm-gateway>/Anthropic (cross-host Claude stage), SQLite audit DB (AUDIT_DB)
cc_cross_host=1
pass=15   fail=0
agentic=ok
```

## What was proven (all HARD checks green)

| Stage | Check | Result |
|-------|-------|--------|
| 0 | connector unit tests green; `GATEWAY_KEY` set; gaia cloned + importable in venv | PASS |
| 3 | **gaia's own MCP client connects + lists the `run` tool** (`tools=['run','session_info']`) | PASS |
| 4 | **gaia-driven `run` returned real sandbox output** (`GAIA_OK` + hostname) | PASS |
| 4 | gaia-driven `run` produced `decision=allow` in the audit DB | PASS |
| 4 | **gaia event (session `gaia-probe`) CONFIRMED in the SQLite audit DB** via SQL read-back | PASS |
| 5 | [cross-host] Claude Code emitted `mcp__axis__run` | PASS |
| 5 | [cross-host] Claude-Code event (session `cc-gaia`) CONFIRMED in the SQLite audit DB | PASS |
| 6 | **gaia Agent (LLM = Qwen3-8B-GGUF on CPU via local Lemonade) called the tool; event (session `gaia-agent`) CONFIRMED in the SQLite audit DB** | PASS |
| 7 | the SQLite audit DB holds a **gaia** toolcall AND a **Claude-Code** toolcall — one connector, two hosts | PASS |

The same `axis_mcp_connector` (unchanged) was driven by **both** gaia and Claude Code, and the
SQLite audit DB holds audited `axis.toolcall` events from both — the core "the connector works with
both Claude Code and gaia" claim, proven by reading events back out of the DB with SQL.

## gaia deterministic probe read-back

```
gaia MCPClient sees tools: ['run', 'session_info']
---- tool output ----
GAIA_OK
node-1
[exit 0]
---------------------
```

## Stage 6 (agentic) — PASS via a local Lemonade 8B model

A gaia `Agent` whose LLM is **`Qwen3-8B-GGUF` served on CPU by the local Lemonade server**
(`:13305`, reused from `stack/lemonade`) decided on its own to call the
connector's `run` tool. The model planned, invoked `mcp_axis_run` with `echo GAIA_AGENT_OK &&
hostname`, got real sandbox output back, and the `axis.toolcall(decision=allow)` event for session
`gaia-agent` was CONFIRMED in the SQLite audit DB.

gaia reaches this via its **native Lemonade provider** (`use_claude=False`, `LEMONADE_BASE_URL`) —
gaia's built-in Claude/OpenAI providers don't honour a custom gateway `base_url`/header, so a local
Lemonade model is the working inference path for gaia's agent loop. (The initial run had requested
`claude-opus-4.8` against Lemonade → `model_not_found`; pointing it at the local 8B model fixed it.)

gaia's final answer:

```
The command `echo GAIA_AGENT_OK && hostname` executed successfully. Here's the output:
    GAIA_AGENT_OK
    node-1
The exit code indicates success (0). The hostname of the machine is `node-1`.
```

## Artifacts

Saved under [`artifacts/node_run/`](./artifacts/node_run/): `SUMMARY.txt`, `run.log`,
`gaia_mcp_list.txt` (gaia connect + tool list), `gaia_probe.out` (real sandbox output),
`gaia_agent.out` (the agentic SKIP detail), `claude_cc.out` (cross-host transcript),
`audit.db` (the SQLite audit DB read back with SQL), `mcp_servers.json` (the gaia registration).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
