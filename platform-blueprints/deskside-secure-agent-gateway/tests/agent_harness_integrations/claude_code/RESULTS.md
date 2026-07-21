<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side SWE-bench test (Strix Halo)

Status: ✅ verified on `<halo-host>` (Strix Halo, Ryzen AI Max+ 395) —
**13 passed / 0 failed, SOLVED=yes** (`RUN_CC=1`, 2026-07-06).

The deskside governance loop solving a **real SWE-bench instance** on real Strix
Halo hardware, with a local **SQLite** audit sink hard-verified by reading the
events back with SQL.

**Inference backend for this verified run: Claude API direct** —
`api.anthropic.com`, model `claude-opus-4-8`. (An `INFERENCE_MODE=gateway` path
to an Anthropic-compatible gateway also exists in the scripts, but it is **not** the backend
used for this result — see Notes.)

## Summary

Claude Code solves `pallets__flask-5014` through the client-side governance loop:
every command it runs funnels through the axis MCP connector's `run` tool →
the AXIS sandbox (sole enforcement) → the local SQLite audit DB. The audit events
are confirmed by **reading them back out of the SQLite DB with SQL** (not just
written), and the code edit is graded (FAIL_TO_PASS) → SOLVED=yes.

| Item | Status |
|------|--------|
| Connector unit tests (32) | ✅ green |
| Task workspace (flask @ base_commit) + py3.11 venv (pytest 7.4.4, werkzeug 2.3.8) | ✅ |
| SQLite audit DB (`AUDIT_DB`, `events` table) | ✅ verified |
| AXIS sandbox (Landlock+seccomp+netns, sole enforcement) | ✅ healthy |
| Inference `/v1/messages` completion (`claude-opus-4-8`) | ✅ verified |
| Claude Code got a real response (`is_error:false`) | ✅ |
| Model emitted `mcp__axis__run` | ✅ |
| Edit persisted to host repo (`src/flask/blueprints.py`) | ✅ |
| toolcall event(s) CONFIRMED in the SQLite audit DB | ✅ read back with SQL |
| session_start CONFIRMED in the SQLite audit DB | ✅ read back with SQL |
| Grade — apply test_patch, FAIL_TO_PASS passes | ✅ **SOLVED=yes** |

## How to reproduce (on Strix Halo)

```bash
cd tests/agent_harness_integrations/claude_code

# Claude API direct (no tunnel):
INFERENCE_MODE=anthropic ANTHROPIC_API_KEY=<key> bash run_swebench_client.sh

# Custom-header gateway instead (needs the laptop tunnel + /etc/hosts alias):
#   laptop:  ssh -N -R 127.0.0.1:8443:<llm-gateway>:443 halo
#   halo:    echo "127.0.0.1 <llm-gateway>" | sudo tee -a /etc/hosts
INFERENCE_MODE=gateway GATEWAY_KEY=<key> bash run_swebench_client.sh
```

The audit DB is a local SQLite file (`AUDIT_DB`, default `artifacts/audit.db`);
the runner starts from a clean DB each run and no external audit service is needed.

## Node-run results (2026-07-06, `<halo-host>`)

`artifacts/SUMMARY.txt`:

```
swebench run @ 2026-07-06T18:50:31Z
host=<halo-host> node=v22.22.2
instance=pallets__flask-5014 model=claude-opus-4-8 gateway=https://api.anthropic.com
audit_db=artifacts/audit.db
solved=yes
pass=13 fail=0
```

The events as recorded in the SQLite audit DB, read back with SQL
(`sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'`):

```
2026-07-06 11:50:16.846 PDT  axis.session_start   decision=-      exit=-
2026-07-06 11:50:16.900 PDT  axis.toolcall        decision=allow  exit=0
2026-07-06 11:50:21.662 PDT  axis.toolcall        decision=allow  exit=0
2026-07-06 11:50:27.475 PDT  axis.toolcall        decision=allow  exit=0

  4 events in the SQLite audit DB
```

## Notes from the verified run (Halo-specific)

Environmental adaptations for the unprivileged Halo node. All inference/limit
knobs are switchable so a privileged node runs unchanged.

1. **AXIS native backend.** The generated swebench policy now sets
   `runtime.provider: axis_native` + zeroed process limits (overridable via
   `AXIS_RUNTIME_PROVIDER` / `AXIS_MAX_PROCESSES` / `AXIS_MAX_MEMORY_MB` /
   `AXIS_CPU_RATE_PERCENT`). Reason: no lxc-exec/netns/writable-cgroups on Halo.
   Consequence: resource-limit enforcement is not exercised here.
2. **Inference-mode switch (`INFERENCE_MODE`).** Added to
   `run_swebench_client.sh` + `claude_job.sh`:
   - `anthropic` — `api.anthropic.com`, `x-api-key`, model `claude-opus-4-8`.
     **This is the backend used for this verified result.**
   - `gateway` — an Anthropic-compatible gateway, `Ocp-Apim-Subscription-Key`, `claude-opus-4.8`.
     Provided as an option but **not exercised in this result**: the gateway
     is not reachable from Halo directly (resolves to an internal address,
     black-holed at the node's only gateway), so it would require a laptop SSH
     reverse tunnel (non-permanent) or IT routing the node to the gateway. We
     default to Claude API direct to remove that dependency.
3. **Audit read-back.** Audit events are written to a local SQLite DB
   (`AUDIT_DB`, default `artifacts/audit.db`) and the checks read them back with
   SQL, so a silent write failure can't produce a false green — the run only
   passes when the events are actually present in the DB.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
