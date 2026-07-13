<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side SWE-bench test on a Strix Halo deskside

Reference target: one machine (has `axis`, outbound internet, and a real Splunk).

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the gateway | inference plane | `curl -sI https://<llm-gateway>` |
| outbound internet | clone flask + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox | `command -v axis` |
| Node ≥18 + npm | connector | `node --version` |
| Python 3.11 (or `uv`) + git | flask task venv + clone | `python3.11 --version` / `uv --version` |
| `claude` | the functional stage | `command -v claude` |
| `GATEWAY_KEY` | gateway subscription key | *(provided at launch)* |
| real Splunk | audit sink | reuse the shared `~/splunk`, or `SPLUNK_URL`/`SPLUNK_TGZ` |

The sibling tree `../../../stack` (including `../../../stack/splunk`) and the vendored `./task`
directory must be present alongside this folder — this test reuses them by relative path.

## One-shot end-to-end

```bash
cd tests/agent_harness_integrations/claude_code
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_swebench_client.sh
```

If a real Splunk is already running and the creds authenticate, the runner **reuses it** and skips
the install. On the reference machine pass `SPLUNK_PASS=<SPLUNK_PASS>` and
`HEC_TOKEN=<HEC_TOKEN>` so the connector and the search-verification use the
instance's real token. Otherwise pass `SPLUNK_URL=<splunk-ent-tgz-url>` to install fresh.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node, axis, connector deps + the connector unit tests, `GATEWAY_KEY`, python3/git.
1. **task workspace** — clone `pallets/flask` @ base_commit into `artifacts/workspace`; build a
   py3.11 task venv (flask editable, pytest 7.4.4, werkzeug 2.3.8); generate `axis-swebench.yaml`
   granting `read_write` on the workspace (so edits persist to host).
2. **real Splunk** — reuse-or-install; HEC + mgmt/search API health.
3. **DefenseClaw gateway** — `:18970` action mode; token minted + propagated.
4. **gateway preflight** — `POST /v1/messages` returns a real `claude-opus-4.8` completion.
5. **functional solve (HARD)** — Claude Code (cwd = workspace) emits `mcp__axis__run`, edits
   `blueprints.py` (persisted to host), events confirmed in `index=axis` via the search API.
6. **grade (soft)** — apply `test_patch`, run FAIL_TO_PASS → `SOLVED=yes/no` (reported only).

Useful env overrides: `GATEWAY_URL`, `MODEL` (default `claude-opus-4.8`), `SPLUNK_PASS`,
`SPLUNK_HOME`, `WEB_PORT`/`MGMT_PORT`/`HEC_PORT`, `HEC_TOKEN`, `DC_PORT`, `AXIS_BIN`, `TASKVENV`,
`RUN_CC=0` (skip the functional stage), `CC_TIMEOUT`, `MAXTURNS`.

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/instance/model/up flags + `solved`.
- `claude_cc.out` — the Claude-Code stream-json transcript (tool_use + result).
- `events.jsonl` — the local copy of events the connector built.
- `splunk_query.txt` — the events **as Splunk indexed them** (search API), the real proof.
- `grade.out` / `grade_pytest.txt` — the FAIL_TO_PASS result.
- `gateway_messages_probe.json`, `splunk_install.log`, `gateway_boot.txt`.

## Troubleshooting

- **HEC POST silently dropped** — Node's `fetch` rejects Splunk's self-signed cert; the runner sets
  `NODE_TLS_REJECT_UNAUTHORIZED=0` (also in `.mcp.json`).
- **`{"error":"unauthorized"}` from DefenseClaw** — a stale gateway on `DC_PORT`; the runner kills it
  before starting.
- **search returns 0 rows briefly** — indexing lag; the runner polls ~60s. Keep `/` above ~6 GB free
  (Splunk `minFreeSpace` silently halts indexing+search).
- **edit not persisted** — confirm the AXIS policy names the literal absolute workspace path under
  `read_write` (landlock can't follow `{workspace}` indirection).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
