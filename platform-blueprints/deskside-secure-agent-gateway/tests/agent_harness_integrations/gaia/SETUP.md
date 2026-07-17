<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side gaia test on a Strix Halo deskside

Reference target: one machine (has `axis` and outbound internet). Audit is a local SQLite DB.

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the gateway | agentic stage (best-effort) | `curl -sI https://<llm-gateway>` |
| outbound internet | clone gaia + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox (Landlock+seccomp+netns) | `command -v axis` |
| Node ≥18 + npm | connector | `node --version` |
| Python 3.11 (or `uv`) + git | gaia venv + clone | `python3.11 --version` / `uv --version` |
| `claude` | the cross-host stage (Stage 5) | `command -v claude` |
| `GATEWAY_KEY` | gateway subscription key | *(provided at launch)* |

The sibling trees `../../../stack` and `../claude_code`
must be present alongside this folder — this test reuses them by relative path. The
audit sink is a local SQLite DB (`AUDIT_DB`, default `artifacts/audit.db`); no external
audit service is required.

## One-shot end-to-end

```bash
cd tests/agent_harness_integrations/gaia
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
  bash run_gaia_integration.sh
```

Every tool call is enforced by the AXIS sandbox (the sole enforcement layer) and its
`axis.toolcall` event is written to the SQLite audit DB. The runner starts from a clean
`AUDIT_DB` each run so the probes assert on this run's events.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions + gaia install** — node, axis, connector deps + the connector unit tests,
   `GATEWAY_KEY`, python3/git; clone `https://github.com/amd/gaia` into `artifacts/gaia`; build
   `artifacts/gaia-venv` and `pip install -e ".[mcp]"` (fallback `amd-gaia[mcp]`); assert `gaia`
   importable.
3. **register with gaia** — write `artifacts/mcp_servers.json` (connector command + full
   AXIS/`AUDIT_DB` env); assert gaia's `MCPClient` connects and lists the `run` tool.
4. **gaia deterministic probe (HARD)** — `gaia_mcp_probe.py` drives the connector's `run` under
   session `gaia-probe`; real sandbox output + `axis.toolcall(decision=allow)` event confirmed by
   reading it back out of the SQLite audit DB.
5. **cross-host (Claude Code)** — `../claude_code/claude_job.sh` runs a run-tool call
   under session `cc-gaia`; event confirmed in the SQLite audit DB. (`RUN_CC=0` skips.)
6. **gaia agentic (best-effort)** — `gaia_agent_query.py` asks a gaia `Agent` (LLM = `Qwen3-8B-GGUF`
   on CPU via the local Lemonade server, reused-or-booted via `../../../stack/lemonade`) to call
   the tool under session `gaia-agent`; confirmed → `agentic=ok`, else reported `agentic=skip`.
   (`RUN_AGENTIC=0` skips; `LEMON_MODEL`/`LEMONADE_PORT` override the model/port.)
7. **cross-host proof** — assert the SQLite audit DB holds both a gaia session and a Claude-Code session.
8. **summary** — `artifacts/SUMMARY.txt` (SQLite event count).

Useful env overrides: `GATEWAY_URL`, `MODEL` (default `claude-opus-4.8`), `AUDIT_DB`,
`AXIS_BIN`, `AXIS_POLICY`, `GAIA_REPO`, `GAIA_VENV`, `RUN_CC=0` (skip cross-host Claude stage),
`RUN_AGENTIC=0` (skip agentic stage), `LEMON_MODEL` (default `Qwen3-8B-GGUF`),
`LEMONADE_PORT` (default `13305`), `LEMONADE_BASE_URL`.

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/node/model/up flags + `agentic=ok/skip`.
- `gaia_mcp_list.txt` — gaia's MCP client connect result + tool list (proves gaia speaks to it).
- `gaia_probe.out` — the deterministic probe's real sandbox output (`GAIA_OK` + hostname).
- `gaia_agent.out` / `gaia_agent.err` — the agentic stage transcript / `AGENTIC_SKIP` reason.
- `claude_cc.out` — the cross-host Claude-Code stream-json transcript.
- `audit.db` — the SQLite audit DB; read the `axis.toolcall` events back with SQL, e.g.
  `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'` — the real proof.

## Troubleshooting

- **gaia install fails** — the runner falls back to `pip install "amd-gaia[mcp]"`; check
  `gaia_install.log`. If neither works, Stage 0's "gaia importable" check fails fast.
- **audit DB empty / probe can't confirm an event** — the connector writes to `AUDIT_DB`
  (default `artifacts/audit.db`); make sure that path is writable and that the same `AUDIT_DB`
  is exported to both the connector env in `mcp_servers.json` and the read-back helper.
- **low disk space** — keep `/` with a few GB free so the SQLite write and the gaia venv/clone
  don't fail mid-run.
- **agentic stage SKIP** — the agentic stage drives gaia's native Lemonade provider against a local
  `Qwen3-8B-GGUF` on CPU. If the Lemonade server on `:13305` isn't up (and can't be booted), Stage 6
  is reported SKIP — the Stage 4 deterministic probe still HARD-proves the integration. If gaia 404s
  with `model_not_found`, the requested `GAIA_MODEL` isn't served locally; set `LEMON_MODEL` to a
  model the Lemonade server actually has (`curl -s :13305/api/v1/models`).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
