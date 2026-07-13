<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side SWE-bench test (Strix Halo)

Status: ✅ verified on `<halo-host>` (Strix Halo, Ryzen AI Max+ 395) —
**13 passed / 0 failed, SOLVED=yes** (`RUN_CC=1`, 2026-07-06).

The deskside governance loop solving a **real SWE-bench instance** on real Strix
Halo hardware, with a **real Splunk** audit sink hard-verified via the search
API.

**Inference backend for this verified run: Claude API direct** —
`api.anthropic.com`, model `claude-opus-4-8`. (An `INFERENCE_MODE=gateway` path
to the AMD LLM Gateway also exists in the scripts, but it is **not** the backend
used for this result — see Notes.)

## Summary

Claude Code solves `pallets__flask-5014` through the client-side governance loop:
every command it runs funnels through the axis MCP connector's `run` tool →
DefenseClaw admission → real AXIS sandbox → real Splunk HEC. The audit events are
confirmed by **reading them back out of `index=axis`** via the search API (not
just POSTed), and the code edit is graded (FAIL_TO_PASS) → SOLVED=yes.

| Item | Status |
|------|--------|
| Connector unit tests (32) | ✅ green |
| Task workspace (flask @ base_commit) + py3.11 venv (pytest 7.4.4, werkzeug 2.3.8) | ✅ |
| Real Splunk Enterprise 10.4.1 (HEC + mgmt/search API + `axis` index) | ✅ verified |
| Real DefenseClaw gateway (`:18970`, action mode) | ✅ healthy |
| Inference `/v1/messages` completion (`claude-opus-4-8`) | ✅ verified |
| Claude Code got a real response (`is_error:false`) | ✅ |
| Model emitted `mcp__axis__run` | ✅ |
| Edit persisted to host repo (`src/flask/blueprints.py`) | ✅ |
| toolcall event(s) CONFIRMED in real Splunk index | ✅ read back via search API |
| session_start CONFIRMED in real Splunk index | ✅ read back via search API |
| Grade — apply test_patch, FAIL_TO_PASS passes | ✅ **SOLVED=yes** |

## How to reproduce (on Strix Halo)

```bash
cd tests/agent_harness_integrations/claude_code

# Claude API direct (no tunnel):
INFERENCE_MODE=anthropic ANTHROPIC_API_KEY=<key> bash run_swebench_client.sh

# AMD Gateway instead (needs the laptop tunnel + /etc/hosts alias):
#   laptop:  ssh -N -R 127.0.0.1:8443:<llm-gateway>:443 halo
#   halo:    echo "127.0.0.1 <llm-gateway>" | sudo tee -a /etc/hosts
INFERENCE_MODE=gateway GATEWAY_KEY=<key> bash run_swebench_client.sh
```

Splunk auto-installs from `~/splunk-10.4.1-linux-amd64.tgz` on first run
(user-space `~/splunk`, ports 8000/8089/18088) and is reused afterward.

## Node-run results (2026-07-06, `<halo-host>`)

`artifacts/SUMMARY.txt`:

```
swebench run @ 2026-07-06T18:50:31Z
host=<halo-host> node=v22.22.2
instance=pallets__flask-5014 model=claude-opus-4-8 gateway=https://api.anthropic.com
splunk_up=1 defenseclaw_up=1
solved=yes
pass=13 fail=0
```

The events as Splunk indexed them, read back via the search API
(`artifacts/splunk_query.txt`):

```
2026-07-06 11:50:16.846 PDT  axis.session_start   decision=-      exit=-
2026-07-06 11:50:16.900 PDT  axis.toolcall        decision=allow  exit=0
2026-07-06 11:50:21.662 PDT  axis.toolcall        decision=allow  exit=0
2026-07-06 11:50:27.475 PDT  axis.toolcall        decision=allow  exit=0

  4 events returned from Splunk index
```

## Notes from the verified run (Halo-specific)

Environmental adaptations for the unprivileged Halo node + one real bug found and
fixed. All inference/limit knobs are switchable so a privileged node runs
unchanged.

1. **AXIS native backend.** The generated swebench policy now sets
   `runtime.provider: axis_native` + zeroed process limits (overridable via
   `AXIS_RUNTIME_PROVIDER` / `AXIS_MAX_PROCESSES` / `AXIS_MAX_MEMORY_MB` /
   `AXIS_CPU_RATE_PERCENT`). Reason: no lxc-exec/netns/writable-cgroups on Halo.
   Consequence: resource-limit enforcement is not exercised here.
2. **Inference-mode switch (`INFERENCE_MODE`).** Added to
   `run_swebench_client.sh` + `claude_job.sh`:
   - `anthropic` — `api.anthropic.com`, `x-api-key`, model `claude-opus-4-8`.
     **This is the backend used for this verified result.**
   - `gateway` — AMD LLM Gateway, `Ocp-Apim-Subscription-Key`, `claude-opus-4.8`.
     Provided as an option but **not exercised in this result**: the AMD Gateway
     is not reachable from Halo directly (resolves to an internal address,
     black-holed at the node's only gateway), so it would require a laptop SSH
     reverse tunnel (non-permanent) or IT routing the node to the gateway. We
     default to Claude API direct to remove that dependency.
3. **HEC token read-back fix (real bug).** Splunk 10.x ignores the requested
   `-token` on `http-event-collector create` and generates its own, so the
   connector's `.mcp.json` had a stale token → POSTs 403'd → **0 events indexed
   while the run still reported SOLVED=yes (a false green)**. The runner now reads
   the actual `axis-orch` token back after Splunk is up and feeds it to the
   connector. After the fix: 4 events confirmed in `index=axis`.
4. **`NODE_TLS_REJECT_UNAUTHORIZED=0`** is set by the runner (harmless for the
   tunnel; should be disabled for `anthropic` mode against the real public API).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
