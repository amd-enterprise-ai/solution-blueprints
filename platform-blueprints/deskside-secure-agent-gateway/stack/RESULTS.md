<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side integration (Strix Halo)

Status: ✅ verified on `<halo-host>` (Strix Halo, Ryzen AI Max+ PRO 395) —
**15 passed / 0 failed** (`RUN_CC=0`, 2026-07-13).

This is the **deskside governance loop running on real Strix Halo hardware**
(AMD Ryzen AI Max+ 395, unprivileged) — a single machine, no orchestrator and no
rack control plane.

## Functional governance loop — 15 checks, grouped by stage

The client-side governance loop (axis MCP connector + inference proxy →
DefenseClaw admission → real AXIS sandbox → Splunk HEC) runs end-to-end on Strix
Halo: the stack comes up, ALLOW runs sandboxed while BLOCK is stopped **before**
AXIS executes, and both planes (inference + tool/audit) correlate under one
`identity.session`. **15 passed / 0 failed** (`RUN_CC=0`, 2026-07-13). These verify
the loop does the *right* thing on normal traffic — the functional complement to the
adversarial Red-Team · 20 below.

| # | Check | What it proves | Result |
|---|-------|----------------|:---:|
| **① Stack build & health — every component comes up · 6 / 6** | | | |
| 1 | connector unit tests (39) | connector suite green (`# fail 0`) | ✅ PASS |
| 2 | inference proxy healthy | `lemonade_proxy` up (inference-plane entry) | ✅ PASS |
| 3 | DefenseClaw gateway healthy | real admission gateway answering on its REST port | ✅ PASS |
| 4 | Lemonade server healthy | Qwen3-8B served locally on the APU (`/api/v1/health`) | ✅ PASS |
| 5 | Lemonade returns a completion | the model actually answers a prompt (real inference) | ✅ PASS |
| 6 | Splunk HEC sink healthy | audit sink reachable before any tool call runs | ✅ PASS |
| **② Admission + sandbox enforcement — ALLOW runs, BLOCK is stopped · 6 / 6** | | | |
| 7 | ALLOW ran in real AXIS | allowed command produced real sandboxed output (`ROCM_OK`) | ✅ PASS |
| 8 | ALLOW recorded `decision=allow` | the allowed call is on the record as allowed | ✅ PASS |
| 9 | DefenseClaw saw the call | admission was actually consulted (`reachable:true`) | ✅ PASS |
| 10 | BLOCK on ssh-key read (action mode) | DefenseClaw blocks a sensitive-path read at admission | ✅ PASS |
| 11 | BLOCK recorded `decision=block` | the blocked call is on the record as blocked | ✅ PASS |
| 12 | blocked call has `exit:null` | AXIS **never executed** the blocked command | ✅ PASS |
| **③ Audit trail + cross-plane correlation — nothing runs unrecorded · 3 / 3** | | | |
| 13 | `axis.toolcall` landed in the sink | every tool call emits an audit event | ✅ PASS |
| 14 | `axis.session_start` emitted | the session is opened on the record | ✅ PASS |
| 15 | one `identity.session` across both planes | inference (`llm.request`) + tool (`axis.toolcall`) correlate | ✅ PASS |

Beyond the 15: the **75 proxy** unit tests are green too (cross-plane session,
OTEL, trace, GPU — these run outside the loop and are not double-counted), and
`defenseclaw-gateway` builds via `make gateway`. The one *best-effort* item **not**
counted in the 15 — the local 8B reliably emitting `mcp__axis__run` under
`RUN_CC=1` — is a model limitation (not wiring, not a governance check), so it is
excluded from the pass count.

Bring-up and run steps live in [`SETUP.md`](./SETUP.md)
(`source platforms/halo/env.sh` → `bash platforms/halo/setup.sh` → `bash platforms/halo/run.sh`).

## Red-team (adversarial) results

The functional loop above proves the governance stack does the *right* thing; the
red-team suite proves it holds when something tries to break it. Same box, same
stack, run in-place via `run_redteam.sh`:

**20 / 20 adversarial probes CONTAINED** — regression gate, 2026-07-13,
`<halo-host>`, exit 0. Every probe was stopped at a defined layer
(**L1** DefenseClaw admission / **L2** AXIS sandbox / **L3** fail-closed audit) *and*
recorded in the audit trail. By attacker goal: **10/10 steal-data · 5/5 break-out ·
5/5 defeat-controls**. (The harness emits 21 result rows: RT-001a is a
non-adversarial baseline that confirms the L1 rule fires on the un-obfuscated
form, so it is not counted as an attack — see `REDTEAM_FINDINGS.md`.) Three were breaches when first probed and are now closed
(RT-005/006/007), each fix flag-gated so existing workloads are unaffected.

Full per-probe evidence, the end-to-end kill-chain walk-through and the coverage
matrix live in
[`REDTEAM_FINDINGS.md`](./REDTEAM_FINDINGS.md) — not duplicated here. Reproduce:

```bash
REDTEAM_MODE=regression bash run_redteam.sh                 # non-zero on any BREACH
REDTEAM_REAL_SPLUNK=1 SPLUNK_PASS=<pw> REDTEAM_MODE=regression bash run_redteam.sh  # to real Splunk
```

## v1.0 telemetry deltas (AMD⇄Cisco) — verified on this box (2026-07-08)

The three telemetry deltas Cisco asked for are implemented and verified end-to-end
on real Strix Halo hardware, into **real Splunk** (`index=axis`):

| Delta | Status | Evidence |
|-------|--------|----------|
| **GPU consumption on local inference** | ✅ | `llm.request.gpu` block from amdgpu sysfs (no ROCm): under load busy 57→74%, power 54→62 W, energy 40→53 J/turn, VRAM ~7.8 GB. Splunk: `stats sum(gpu.energy_joules) by request.model` → 93.9 J for Qwen3-8B. |
| **OTEL-shaped events** | ✅ | every event carries `event_id`, `schema_version=1.0`, `ingest_source`, `trace_id`/`span_id`/`parent_span_id`, `resource{service.*}`; `llm.request` carries GenAI `attributes` (`gen_ai.request.model`, `gen_ai.usage.*`, `gen_ai.provider.name`, `execution_location`). |
| **Per-turn trace_id** | ✅ | proxy detects a new user turn, mints a trace to the shared `AXIS_TRACE_STATE` statefile; connector reads it. One 2-turn session → **2 trace_ids**, each grouping its `llm.request` + `axis.toolcall` across both planes. |

- **Local stack, all local:** AXIS 0.3.5 (built from `qedawkins/axis@mxc`),
  DefenseClaw gateway 0.8.0, **real Splunk Enterprise** (HEC :8088, `index=axis`),
  Lemonade 9.1.4 serving Qwen3-8B-GGUF on the APU.
- **Note (this box):** the pip Lemonade build serves the **OpenAI** API, not
  Anthropic `/v1/messages`; the proxy forwards it byte-for-byte and its telemetry
  parser reads both shapes. The session capture is driven by the deterministic
  scripted probe (OpenAI chat/completions through the proxy + `mcp_probe` tool
  calls) — see `make_cisco_session.sh`. Also: `/tmp` is `noexec`, so Rust/Lemonade
  need an exec-capable `TMPDIR` (`platforms/halo/env.sh` sets `$HALO_TOOLS/tmp`),
  and Node/Python need the system CA bundle (`NODE_EXTRA_CA_CERTS` /
  `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`).
- **Deliverable:** `bash make_cisco_session.sh` → `artifacts/cisco_session_<ts>/`
  (`events.ndjson`, `by_trace.md`, `README.md`, `SCHEMA.md`) + a `.tgz` to send.
- Tests: 39 connector + 75 proxy, all green. Functional loop 15/0. Red-team
  regression (2026-07-13): all 20 probes CONTAINED.

## Raw run evidence (2026-07-13, `<halo-host>`)

The captured artifacts behind the 15/0 table above — machine-generated, not asserted.

`artifacts/SUMMARY.txt`:

```
15 passed / 0 failed
gateway run @ 2026-07-13T10:09:36Z
host=<halo-host> node=v22.23.1
defenseclaw_up=1 lemonade_up=1 proxy_up=1
unified_session=1
pass=15 fail=0
```

The two hard governance checks, as captured (`artifacts/events.jsonl`,
`artifacts/hec_capture.jsonl`):

- **ALLOW** — `bash -c "echo ROCM_OK && hostname"` ran in the real AXIS sandbox
  (`decision=allow`, `exit:0`, `duration_ms:20`); the `axis.toolcall` +
  `axis.session_start` events carry `tenant=client-deskside`,
  `device_id=<halo-host>`, one `identity.session`.
- **BLOCK** — an SSH-key path access tripped DefenseClaw
  (`severity=CRITICAL`, findings `PATH-SSH-DIR`, `PATH-SSH-KEY`); the call was
  `[blocked by DefenseClaw]` and **AXIS never executed it**.

Example ALLOW event (`events.jsonl`):

```json
{"event":"axis.toolcall","identity":{"session":"cc-itest-unified-<uuid>","user":"user","tenant":"client-deskside","device_id":"<halo-host>"},"command":{"argv_redacted":["bash","-c","echo ROCM_OK && hostname"]},"decision":"allow","result":{"exit":0,"duration_ms":20},"defenseclaw":{"action":"allow","severity":"NONE","reachable":true}}
```

## Notes from the verified run (Halo-specific)

These are environmental adaptations for an unprivileged, shared Strix Halo node
— not connector/test changes. All are switchable so a privileged node is
unaffected.

1. **AXIS native backend.** The repo's `coding-agent.yaml` needs lxc-exec +
   netns + writable cgroups (privileged). On Halo we point `AXIS_POLICY` at the
   committed `platforms/halo/axis-policy-native.yaml` — `runtime.provider: axis_native`
   (Landlock + seccomp), `network: block`, and **zeroed process limits** (AXIS
   fails closed if it can't enforce a requested limit without writable
   cgroups v2). Consequence: cgroups resource-limit enforcement is not exercised
   here — the connector's userspace `ulimit` fallback covers it (see
   `REDTEAM_FINDINGS.md` RT-007).
2. **AXIS built from source** (`qedawkins/axis`, Rust) into `$HALO_TOOLS/bin` by
   `platforms/halo/setup.sh`; the seccomp launcher refuses a group-writable install path,
   so the whole ancestry is 755.
3. **Audit sink defaults to the local fake HEC** (`fake_hec.py`) for a
   self-contained run — 11 events captured on the recorded run. The same loop
   also ships to **real Splunk** (`index=axis`) with `REAL_SPLUNK=1` (governance
   loop) / `REDTEAM_REAL_SPLUNK=1` (red-team); the connector dual-writes the local
   mirror and the real HEC, so enforcement is identical either way.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
