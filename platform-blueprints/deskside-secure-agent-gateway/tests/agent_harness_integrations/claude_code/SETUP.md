<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side SWE-bench test on a Strix Halo deskside

Reference target: one machine (has `axis` and outbound internet). Audit is a local SQLite DB.

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the gateway | inference plane | `curl -sI https://<llm-gateway>` |
| outbound internet | clone flask + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox (Landlock+seccomp+netns) | `command -v axis` |
| Node ≥18 + npm | connector | `node --version` |
| Python 3.11 (or `uv`) + git | flask task venv + clone | `python3.11 --version` / `uv --version` |
| `claude` | the functional stage | `command -v claude` |
| `GATEWAY_KEY` | gateway subscription key | *(provided at launch)* |

The sibling tree `../../../stack` and the vendored `./task` directory must be present alongside this
folder — this test reuses them by relative path. The audit sink is a local SQLite DB (`AUDIT_DB`,
default `artifacts/audit.db`); no external audit service is required.

## One-shot end-to-end

```bash
cd tests/agent_harness_integrations/claude_code
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
  bash run_swebench_client.sh
```

Every tool call is enforced by the AXIS sandbox (the sole enforcement layer) and its
`axis.toolcall` event is written to the SQLite audit DB. The runner starts from a clean `AUDIT_DB`
each run so the checks assert on this run's events.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node, axis, connector deps + the connector unit tests, `GATEWAY_KEY`, python3/git.
1. **task workspace** — clone `pallets/flask` @ base_commit into `artifacts/workspace`; build a
   py3.11 task venv (flask editable, pytest 7.4.4, werkzeug 2.3.8); generate `axis-swebench.yaml`
   granting `read_write` on the workspace (so edits persist to host).
2. **gateway preflight** — `POST /v1/messages` returns a real `claude-opus-4.8` completion.
3. **functional solve (HARD)** — Claude Code (cwd = workspace) emits `mcp__axis__run`, edits
   `blueprints.py` (persisted to host); `axis.toolcall(decision=allow)` + `axis.session_start`
   confirmed by reading them back out of the SQLite audit DB.
4. **grade (soft)** — apply `test_patch`, run FAIL_TO_PASS → `SOLVED=yes/no` (reported only).

Useful env overrides: `GATEWAY_URL`, `MODEL` (default `claude-opus-4.8`), `AUDIT_DB`, `AXIS_BIN`,
`AXIS_POLICY`/`AXIS_RUNTIME_PROVIDER`, `TASKVENV`, `RUN_CC=0` (skip the functional stage),
`CC_TIMEOUT`, `MAXTURNS`.

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/instance/model + `solved`.
- `claude_cc.out` — the Claude-Code stream-json transcript (tool_use + result).
- `audit.db` — the SQLite audit DB; read the events back with SQL, e.g.
  `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'` — the real proof.
- `grade.out` / `grade_pytest.txt` — the FAIL_TO_PASS result.
- `gateway_messages_probe.json`, `unit_tests.log`, `npm_install.log`.

## Troubleshooting

- **audit DB empty / checks can't confirm an event** — the connector writes to `AUDIT_DB`
  (default `artifacts/audit.db`); make sure that path is writable and that the same `AUDIT_DB`
  is set in the connector env in `.mcp.json` and in the read-back helper.
- **low disk space** — keep `/` with a few GB free so the SQLite write and the flask clone/venv
  don't fail mid-run.
- **edit not persisted** — confirm the AXIS policy names the literal absolute workspace path under
  `read_write` (landlock can't follow `{workspace}` indirection).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
