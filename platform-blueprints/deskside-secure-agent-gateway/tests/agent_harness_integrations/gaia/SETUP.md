<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side gaia test on a Strix Halo deskside

Reference target: one machine (has `axis`, outbound internet, and a real Splunk).

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the gateway | agentic stage (best-effort) | `curl -sI https://<llm-gateway>` |
| outbound internet | clone gaia + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox | `command -v axis` |
| Node ≥18 + npm | connector | `node --version` |
| Python 3.11 (or `uv`) + git | gaia venv + clone | `python3.11 --version` / `uv --version` |
| `claude` | the cross-host stage (Stage 5) | `command -v claude` |
| `GATEWAY_KEY` | gateway subscription key | *(provided at launch)* |
| real Splunk | audit sink | reuse the shared `~/splunk`, or `SPLUNK_URL`/`SPLUNK_TGZ` |

The sibling trees `../../../stack`, `../../../stack/splunk`, and `../claude_code/amd_gateway_test`
must be present alongside this folder — this test reuses them by relative path.

## One-shot end-to-end

```bash
cd tests/agent_harness_integrations/gaia
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_gaia_integration.sh
```

If a real Splunk is already running and the creds authenticate, the runner **reuses it** and skips
the install. On the reference machine pass `SPLUNK_PASS=<SPLUNK_PASS>` and
`HEC_TOKEN=<HEC_TOKEN>` so the connector and the search-verification use the
instance's real token. Otherwise pass `SPLUNK_URL=<splunk-ent-tgz-url>` to install fresh.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node, axis, connector deps + the connector unit tests, `GATEWAY_KEY`, python3/git; clone
   `https://github.com/amd/gaia` into `artifacts/gaia`; build `artifacts/gaia-venv` and
   `pip install -e ".[mcp]"` (fallback `amd-gaia[mcp]`); assert `gaia` importable.
1. **real Splunk** — reuse-or-install; HEC + mgmt/search API health.
2. **DefenseClaw gateway** — `:18970` action mode; token minted + propagated; connector env exported.
3. **register with gaia** — write `artifacts/mcp_servers.json` (connector command + full
   AXIS/DefenseClaw/Splunk env); assert gaia's `MCPClient` connects and lists the `run` tool.
4. **gaia deterministic probe (HARD)** — `gaia_mcp_probe.py` drives the connector's `run` under
   session `gaia-probe`; real sandbox output + event confirmed in `index=axis` via the search API.
5. **cross-host (Claude Code)** — `../claude_code/amd_gateway_test/claude_job.sh` runs a run-tool call
   under session `cc-gaia`; event confirmed in Splunk. (`RUN_CC=0` skips.)
6. **gaia agentic** — `gaia_agent_query.py` asks a gaia `Agent` (LLM = `Qwen3-8B-GGUF` on CPU via
   the local Lemonade server, reused-or-booted via `../../../stack/lemonade`) to call
   the tool under session `gaia-agent`; confirmed → `agentic=ok`, else reported `agentic=skip`.
   (`RUN_AGENTIC=0` skips; `LEMON_MODEL`/`LEMONADE_PORT` override the model/port.)
7. **cross-host proof** — assert `index=axis` holds both a gaia session and a Claude-Code session.
8. **summary** — `artifacts/SUMMARY.txt` + the search read-back into `artifacts/splunk_query.txt`.

Useful env overrides: `GATEWAY_URL`, `MODEL` (default `claude-opus-4.8`), `SPLUNK_PASS`,
`SPLUNK_HOME`, `WEB_PORT`/`MGMT_PORT`/`HEC_PORT`, `HEC_TOKEN`, `DC_PORT`, `AXIS_BIN`, `GAIA_REPO`,
`GAIA_VENV`, `RUN_CC=0` (skip cross-host Claude stage), `RUN_AGENTIC=0` (skip agentic stage),
`LEMON_MODEL` (default `Qwen3-8B-GGUF`), `LEMONADE_PORT` (default `13305`), `LEMONADE_BASE_URL`.

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/node/model/up flags + `agentic=ok/skip`.
- `gaia_mcp_list.txt` — gaia's MCP client connect result + tool list (proves gaia speaks to it).
- `gaia_probe.out` — the deterministic probe's real sandbox output (`GAIA_OK` + hostname).
- `gaia_agent.out` / `gaia_agent.err` — the agentic stage transcript / `AGENTIC_SKIP` reason.
- `claude_cc.out` — the cross-host Claude-Code stream-json transcript.
- `events.jsonl` — the local copy of events the connector built.
- `splunk_query.txt` — the events **as Splunk indexed them** (search API), the real proof.

## Troubleshooting

- **gaia install fails** — the runner falls back to `pip install "amd-gaia[mcp]"`; check
  `gaia_install.log`. If neither works, Stage 0's "gaia importable" check fails fast.
- **HEC POST silently dropped** — Node's `fetch` rejects Splunk's self-signed cert; the runner sets
  `NODE_TLS_REJECT_UNAUTHORIZED=0` (also in `mcp_servers.json`).
- **`{"error":"unauthorized"}` from DefenseClaw** — a stale gateway on `DC_PORT`; the runner kills it
  before starting.
- **search returns 0 rows briefly** — indexing lag; the runner polls ~60s. Keep `/` above ~6 GB free
  (Splunk `minFreeSpace` silently halts indexing+search).
- **agentic stage SKIP** — the agentic stage drives gaia's native Lemonade provider against a local
  `Qwen3-8B-GGUF` on CPU. If the Lemonade server on `:13305` isn't up (and can't be booted), Stage 6
  is reported SKIP — the Stage 4 deterministic probe still HARD-proves the integration. If gaia 404s
  with `model_not_found`, the requested `GAIA_MODEL` isn't served locally; set `LEMON_MODEL` to a
  model the Lemonade server actually has (`curl -s :13305/api/v1/models`).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
