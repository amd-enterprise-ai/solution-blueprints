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
  README.md  RESULTS.md
  run_gaia_integration.sh   end-to-end runner (the main new code)
  gaia_mcp_probe.py         deterministic HARD proof: gaia's MCPClient drives the connector's run
  gaia_agent_query.py       best-effort agentic: a gaia Agent calls the tool via the gateway
  artifacts/                outputs (SUMMARY.txt, audit.db, gaia_*.out, …)
```

## Setup & run

### Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the endpoint | cross-host inference | `curl -sI https://your-gateway` |
| outbound internet | clone gaia + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox (Landlock+seccomp+netns) | put it on PATH with `source ../../../stack/platforms/halo/env.sh` (binary built by `setup.sh`); verify `command -v axis` |
| Node 22 + npm | connector + Claude Code | `node --version && npm --version` |
| Python 3.11 (or `uv`) + git | gaia venv + clone | `python3.11 --version` / `uv --version` |
| `claude` (Claude Code CLI, **known-good 2.1.121**) | the cross-host stage (Stage 5) | `claude --version` — newer builds defer MCP tool loading, which can break the `--allowedTools mcp__axis__run` gating |
| inference access | cross-host Claude stage | set `ANTHROPIC_API_KEY`, or `ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN` (custom-header gateway: `ANTHROPIC_CUSTOM_HEADERS`) |

The sibling trees `../../../stack` and `../claude_code` must be present alongside this folder
(reused by relative path). The audit sink is a local SQLite DB (`AUDIT_DB`, default
`artifacts/audit.db`); no external audit service is required.

### One-shot end-to-end

```bash
cd tests/agent_harness_integrations/gaia

# Option 1 — Anthropic API directly
ANTHROPIC_API_KEY=<key> bash run_gaia_integration.sh

# Option 2 — Anthropic-compatible gateway (bearer token)
ANTHROPIC_BASE_URL=https://your-gateway ANTHROPIC_AUTH_TOKEN=<token> bash run_gaia_integration.sh
```

The runner starts from a clean `AUDIT_DB` each run so the probes assert on this run's events.
Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions + gaia install** — node, axis, connector deps + the connector unit tests,
   inference access, python3/git; clone `https://github.com/amd/gaia` into `artifacts/gaia`, pinned
   to the verified commit `a441765` (override with `GAIA_COMMIT=<sha>`); build `artifacts/gaia-venv`
   and `pip install -e ".[mcp]"` (fallback `amd-gaia[mcp]`); assert `gaia` importable.
3. **register with gaia** — write `artifacts/mcp_servers.json` (connector command + full
   AXIS/`AUDIT_DB` env); assert gaia's `MCPClient` connects and lists the `run` tool.
4. **gaia deterministic probe (HARD)** — `gaia_mcp_probe.py` drives the connector's `run` under
   session `gaia-probe`; real sandbox output + `axis.toolcall(decision=allow)` event confirmed by
   reading it back out of the SQLite audit DB.
5. **cross-host (Claude Code)** — `../claude_code/claude_job.sh` runs a run-tool call under session
   `cc-gaia`; event confirmed in the SQLite audit DB. (`RUN_CC=0` skips.)
6. **gaia agentic (best-effort)** — `gaia_agent_query.py` asks a gaia `Agent` (LLM = `Qwen3-8B-GGUF`
   on CPU via the local Lemonade server, reused-or-booted via `../../../stack/lemonade`) to call the
   tool under session `gaia-agent`; confirmed → `agentic=ok`, else reported `agentic=skip`.
   (`RUN_AGENTIC=0` skips; `LEMON_MODEL`/`LEMONADE_PORT` override the model/port.)
7. **cross-host proof** — assert the SQLite audit DB holds both a gaia session and a Claude-Code session.
8. **summary** — `artifacts/SUMMARY.txt` (SQLite event count).

Useful env overrides: `MODEL` (default `claude-opus-4-8`), `AUDIT_DB`, `AXIS_BIN`, `AXIS_POLICY`,
`GAIA_REPO`, `GAIA_VENV`, `GAIA_COMMIT`, `RUN_CC=0` (skip cross-host Claude stage), `RUN_AGENTIC=0`
(skip agentic stage), `LEMON_MODEL` (default `Qwen3-8B-GGUF`), `LEMONADE_PORT` (default `13305`),
`LEMONADE_BASE_URL`.

### What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/node/model/up flags + `agentic=ok/skip`.
- `gaia_mcp_list.txt` — gaia's MCP client connect result + tool list (proves gaia speaks to it).
- `gaia_probe.out` — the deterministic probe's real sandbox output (`GAIA_OK` + hostname).
- `gaia_agent.out` / `gaia_agent.err` — the agentic stage transcript / `AGENTIC_SKIP` reason.
- `claude_cc.out` — the cross-host Claude-Code stream-json transcript.
- `audit.db` — the SQLite audit DB; read the `axis.toolcall` events back with SQL, e.g.
  `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'` — the real proof.

### Troubleshooting

- **`FATAL: axis binary not found`** — `axis` isn't on PATH. Run
  `source ../../../stack/platforms/halo/env.sh` first (adds `$HALO_TOOLS/bin` to PATH); if it's
  still missing, build it with `bash ../../../stack/platforms/halo/setup.sh`.
- **gaia install fails** — the runner falls back to `pip install "amd-gaia[mcp]"`; check
  `gaia_install.log`. If neither works, Stage 0's "gaia importable" check fails fast.
- **audit DB empty / probe can't confirm an event** — the connector writes to `AUDIT_DB`
  (default `artifacts/audit.db`); ensure that path is writable and the same `AUDIT_DB` is exported
  to both the connector env in `mcp_servers.json` and the read-back helper.
- **low disk space** — keep a few GB free on `/` so the SQLite write and the gaia venv/clone
  don't fail mid-run.
- **agentic stage SKIP** — the agentic stage drives gaia's native Lemonade provider against a local
  `Qwen3-8B-GGUF` on CPU. If the Lemonade server on `:13305` isn't up (and can't be booted), Stage 6
  is reported SKIP — the Stage 4 deterministic probe still HARD-proves the integration. If gaia 404s
  with `model_not_found`, set `LEMON_MODEL` to a model the Lemonade server actually has
  (`curl -s :13305/api/v1/models`).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
