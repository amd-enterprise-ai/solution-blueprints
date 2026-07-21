<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side SWE-bench Test: Claude Code + an Anthropic-compatible endpoint + AXIS + **SQLite audit DB**

Solves one real **SWE-bench** instance (`pallets__flask-5014`) through the **client-side**
governance loop and proves every tool call is audited end-to-end in a local **SQLite audit DB**.

It uses the same control/audit plane as the rest of the blueprint (`axis_mcp_connector`, the AXIS
sandbox as the sole enforcement layer, a local SQLite audit DB) and points it at a real coding task.
This is the single-machine version: there is **no orchestrator and no rack control plane** — the
connector runs each command locally under AXIS and writes the audit event straight to SQLite.

```
            Claude Code (Anthropic-compatible endpoint — bring your own)   (not sandboxed)
                 │ inference: ANTHROPIC_* env (direct key / gateway token / custom header)
                 │ tools: .mcp.json -> ONLY mcp__axis__run
                 ▼
        axis MCP connector (Node, reused from gateway)
                 │ identity -> AXIS sandbox (sole enforcement) -> SQLite audit event
                 ▼
   AXIS sandbox (Landlock+seccomp+netns)              SQLite audit DB
   read_write on the flask workspace                  AUDIT_DB (default artifacts/audit.db)
   (edits persist to host)                            events read back with SQL
```

## What it proves (HARD checks)

1. The configured inference endpoint answers a real completion from the machine.
2. **Functional solve** — real Claude Code, driven by the frontier model, emits `mcp__axis__run`,
   edits `src/flask/blueprints.py` (the edit **persists to the host repo** via the AXIS `read_write`
   rule), and the resulting `axis.toolcall(decision=allow)` + `axis.session_start` events are
   **written to the SQLite audit DB and read back out of it with SQL**.
3. **Grade (soft, reported)** — the official `test_patch` is applied and the FAIL_TO_PASS test
   (`test_empty_name_not_allowed`) is run → `SOLVED=yes/no` recorded in `SUMMARY.txt` (does not gate
   the integration result).

A silent write failure cannot pass: the audit assertions read the event back out of the SQLite DB,
not from an in-memory sink.

## Inference access & platforms

The tool/audit plane is identical everywhere; only where the model runs changes.
Set **one** of these (the runner exits with a how-to if neither is set):

- **Anthropic API directly** — `ANTHROPIC_API_KEY=<key>`.
- **Anthropic-compatible gateway** — `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`
  (bearer token; custom-header gateways use `ANTHROPIC_CUSTOM_HEADERS` — see the
  [main README](../../../README.md)).

**Validated on:**

- **Strix Halo deskside** (Ryzen AI Max+ 395, unprivileged) — the AXIS
  `axis_native` backend (Landlock+seccomp) and zeroed process limits, since the box has no
  lxc/netns helper or writable cgroups-v2; results in [`RESULTS.md`](./RESULTS.md).
  Override `AXIS_RUNTIME_PROVIDER` / `AXIS_*_LIMIT_*` on a machine with those privileges available.

## Reuse (no duplication)

- `../../../stack/axis_mcp_connector/` — connector + the connector unit tests (unchanged)
- `../../lib/audit_db.sh` — shared SQLite audit-DB read-back helpers
- `./task/instance.json` + `grade.sh` — the task definition + deterministic grader (vendored)

## Layout

```
claude_code/
  README.md  RESULTS.md
  run_swebench_client.sh   end-to-end runner (the main new code)
  claude_job.sh            launches Claude Code against the endpoint (run-tool-only, cwd=workspace)
  prompt.txt               the task prompt (uses mcp__axis__run)
  mcp.json.tmpl            .mcp.json template (connector env incl. AUDIT_DB + swebench policy)
  artifacts/               outputs (SUMMARY.txt, audit.db, claude_cc.out, …)
```

## Setup & run

### Prerequisites

| Need | Why | Check |
|------|-----|-------|
| outbound HTTPS to the endpoint | inference plane | `curl -sI https://your-gateway` |
| outbound internet | clone flask + pip/npm deps | `curl -sI https://github.com` |
| `axis` on PATH | the real sandbox (Landlock+seccomp+netns) | put it on PATH with `source ../../../stack/platforms/halo/env.sh` (binary built by `setup.sh`); verify `command -v axis` |
| Node 22 + npm | connector + Claude Code | `node --version && npm --version` |
| Python 3.11 (or `uv`) + git | flask task venv + clone | `python3.11 --version` / `uv --version` |
| `claude` (Claude Code CLI, **known-good 2.1.121**) | the functional stage | `claude --version` — newer builds defer MCP tool loading, which can break the `--allowedTools mcp__axis__run` gating |
| inference access | Anthropic API **or** an Anthropic-compatible gateway (see above) | set `ANTHROPIC_API_KEY`, or `ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN` (custom-header gateway: `ANTHROPIC_CUSTOM_HEADERS`) |

The sibling tree `../../../stack` and the vendored `./task` directory must be present alongside this
folder (reused by relative path). The audit sink is a local SQLite DB (`AUDIT_DB`, default
`artifacts/audit.db`); no external audit service is required.

### One-shot end-to-end

```bash
cd tests/agent_harness_integrations/claude_code

# Option 1 — Anthropic API directly
ANTHROPIC_API_KEY=<key> bash run_swebench_client.sh

# Option 2 — Anthropic-compatible gateway (bearer token)
ANTHROPIC_BASE_URL=https://your-gateway ANTHROPIC_AUTH_TOKEN=<token> bash run_swebench_client.sh
```

The runner starts from a clean `AUDIT_DB` each run so the checks assert on this run's events.
Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node, axis, connector deps + the connector unit tests, inference access, python3/git.
1. **task workspace** — clone `pallets/flask` @ base_commit into `artifacts/workspace`; build a
   py3.11 task venv (flask editable, pytest 7.4.4, werkzeug 2.3.8); generate `axis-swebench.yaml`
   granting `read_write` on the workspace (so edits persist to host).
2. **inference preflight** — `POST /v1/messages` returns a real `claude-opus-4-8` completion.
3. **functional solve (HARD)** — Claude Code (cwd = workspace) emits `mcp__axis__run`, edits
   `blueprints.py` (persisted to host); `axis.toolcall(decision=allow)` + `axis.session_start`
   confirmed by reading them back out of the SQLite audit DB.
4. **grade (soft)** — apply `test_patch`, run FAIL_TO_PASS → `SOLVED=yes/no` (reported only).

Useful env overrides: `MODEL` (default `claude-opus-4-8`), `AUDIT_DB`, `AXIS_BIN`,
`AXIS_POLICY`/`AXIS_RUNTIME_PROVIDER`, `TASKVENV`, `RUN_CC=0` (skip the functional stage),
`CC_TIMEOUT`, `MAXTURNS`.

### What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + host/instance/model + `solved`.
- `claude_cc.out` — the Claude-Code stream-json transcript (tool_use + result).
- `audit.db` — the SQLite audit DB; read events back with SQL, e.g.
  `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'` — the real proof.
- `grade.out` / `grade_pytest.txt` — the FAIL_TO_PASS result.
- `gateway_messages_probe.json`, `unit_tests.log`, `npm_install.log`.

### Troubleshooting

- **`FATAL: axis binary not found`** — `axis` isn't on PATH. Run
  `source ../../../stack/platforms/halo/env.sh` first (adds `$HALO_TOOLS/bin` to PATH); if it's
  still missing, build it with `bash ../../../stack/platforms/halo/setup.sh`.
- **audit DB empty / checks can't confirm an event** — the connector writes to `AUDIT_DB`
  (default `artifacts/audit.db`); ensure that path is writable and the same `AUDIT_DB` is set in
  the connector env in `.mcp.json` and in the read-back helper.
- **low disk space** — keep a few GB free on `/` so the SQLite write and the flask clone/venv
  don't fail mid-run.
- **edit not persisted** — confirm the AXIS policy names the literal absolute workspace path under
  `read_write` (landlock can't follow `{workspace}` indirection).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
