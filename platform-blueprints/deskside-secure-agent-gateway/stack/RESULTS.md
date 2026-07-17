<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side integration (Strix Halo)

Status: ✅ verified on `<halo-host>` (Strix Halo, Ryzen AI Max+ PRO 395) —
**13 passed / 0 failed** (`RUN_CC=0`, 2026-07-13).

This is the **deskside governance loop running on real Strix Halo hardware**
(AMD Ryzen AI Max+ 395, unprivileged) — a single machine, no orchestrator and no
rack control plane.

## Functional governance loop — 13 checks, grouped by stage

The client-side governance loop (axis MCP connector + inference proxy → real AXIS
sandbox → SQLite audit DB) runs end-to-end on Strix Halo: the stack comes up,
ALLOW runs sandboxed, a dangerous command is **contained by AXIS** (the offending
syscall is denied, so the command exits non-zero and is recorded with
`decision=deny`), and both planes (inference + tool/audit) correlate under one
`identity.session`. **13 passed / 0 failed** (`RUN_CC=0`, 2026-07-13). AXIS
(Landlock + seccomp + netns) is the sole tool-plane enforcement layer.

| # | Check | What it proves | Result |
|---|-------|----------------|:---:|
| **① Stack build & health — every component comes up · 5 / 5** | | | |
| 1 | connector unit tests (39) | connector suite green (`# fail 0`) | ✅ PASS |
| 2 | inference proxy healthy | `lemonade_proxy` up (inference-plane entry) | ✅ PASS |
| 3 | Lemonade server healthy | Qwen3-8B served locally on the APU (`/api/v1/health`) | ✅ PASS |
| 4 | Lemonade returns a completion | the model actually answers a prompt (real inference) | ✅ PASS |
| 5 | SQLite audit DB writable | audit sink reachable before any tool call runs | ✅ PASS |
| **② AXIS sandbox enforcement — ALLOW runs, a dangerous command is contained · 5 / 5** | | | |
| 6 | ALLOW ran in real AXIS | allowed command produced real sandboxed output (`ROCM_OK`) | ✅ PASS |
| 7 | ALLOW recorded `decision=allow` | the allowed call is on the record as allowed | ✅ PASS |
| 8 | ssh-key read contained by AXIS | AXIS denies the syscall on a sensitive-path read (non-zero exit) | ✅ PASS |
| 9 | contained call recorded `decision=deny` | the contained call is on the record as denied | ✅ PASS |
| 10 | contained call has non-zero `exit` | AXIS denied the offending syscall at execution time | ✅ PASS |
| **③ Audit trail + cross-plane correlation — nothing runs unrecorded · 3 / 3** | | | |
| 11 | `axis.toolcall` landed in the DB | every tool call emits an audit event | ✅ PASS |
| 12 | `axis.session_start` emitted | the session is opened on the record | ✅ PASS |
| 13 | one `identity.session` across both planes | inference (`llm.request`) + tool (`axis.toolcall`) correlate | ✅ PASS |

Beyond the 13: the **75 proxy** unit tests are green too (cross-plane session,
OTEL, trace, GPU — these run outside the loop and are not double-counted). The one
*best-effort* item **not** counted in the 13 — the local 8B reliably emitting
`mcp__axis__run` under `RUN_CC=1` — is a model limitation (not wiring, not a
governance check), so it is excluded from the pass count.

Bring-up and run steps live in [`SETUP.md`](./SETUP.md)
(`source platforms/halo/env.sh` → `bash platforms/halo/setup.sh` → `bash platforms/halo/run.sh`).

## Telemetry features — verified on this box (2026-07-08)

Three audit-telemetry features are implemented and verified end-to-end on real
Strix Halo hardware, into the local **SQLite audit DB**:

| Delta | Status | Evidence |
|-------|--------|----------|
| **GPU consumption on local inference** | ✅ | `llm.request.gpu` block from amdgpu sysfs (no ROCm): under load busy 57→74%, power 54→62 W, energy 40→53 J/turn, VRAM ~7.8 GB. Aggregated over the audit DB: `SUM(gpu.energy_joules)` grouped by `request.model` → 93.9 J for Qwen3-8B. |
| **OTEL-shaped events** | ✅ | every event carries `event_id`, `schema_version=1.0`, `ingest_source`, `trace_id`/`span_id`/`parent_span_id`, `resource{service.*}`; `llm.request` carries GenAI `attributes` (`gen_ai.request.model`, `gen_ai.usage.*`, `gen_ai.provider.name`, `execution_location`). |
| **Per-turn trace_id** | ✅ | proxy detects a new user turn, mints a trace to the shared `AXIS_TRACE_STATE` statefile; connector reads it. One 2-turn session → **2 trace_ids**, each grouping its `llm.request` + `axis.toolcall` across both planes. |

- **Local stack, all local:** AXIS 0.3.5 (built from `qedawkins/axis@mxc`),
  local **SQLite audit DB**, Lemonade 9.1.4 serving Qwen3-8B-GGUF on the APU.
- **Note (this box):** the pip Lemonade build serves the **OpenAI** API, not
  Anthropic `/v1/messages`; the proxy forwards it byte-for-byte and its telemetry
  parser reads both shapes. The session capture is driven by the deterministic
  scripted probe (OpenAI chat/completions through the proxy + `mcp_probe` tool
  calls). Also: `/tmp` is `noexec`, so Rust/Lemonade
  need an exec-capable `TMPDIR` (`platforms/halo/env.sh` sets `$HALO_TOOLS/tmp`),
  and Node/Python need the system CA bundle (`NODE_EXTRA_CA_CERTS` /
  `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`).
- Tests: 39 connector + 75 proxy, all green. Functional loop 13/0.

## Raw run evidence (2026-07-13, `<halo-host>`)

The captured artifacts behind the 13/0 table above — machine-generated, not asserted.

`artifacts/SUMMARY.txt`:

```
13 passed / 0 failed
gateway run @ 2026-07-13T10:09:36Z
host=<halo-host> node=v22.23.1
lemonade_up=1 proxy_up=1
unified_session=1
pass=13 fail=0
```

The two hard governance checks, as captured (`artifacts/events.jsonl`):

- **ALLOW** — `bash -c "echo ROCM_OK && hostname"` ran in the real AXIS sandbox
  (`decision=allow`, `exit:0`, `duration_ms:20`); the `axis.toolcall` +
  `axis.session_start` events carry `tenant=client-deskside`,
  `device_id=<halo-host>`, one `identity.session`.
- **CONTAINED** — an SSH-key path access was denied by the AXIS sandbox
  (Landlock/seccomp denies the syscall); the command exited non-zero and the call
  was recorded with `decision=deny` — AXIS **contained it at execution time**.

Example ALLOW event (`events.jsonl`):

```json
{"event":"axis.toolcall","identity":{"session":"cc-itest-unified-<uuid>","user":"user","tenant":"client-deskside","device_id":"<halo-host>"},"command":{"argv_redacted":["bash","-c","echo ROCM_OK && hostname"]},"decision":"allow","result":{"exit":0,"duration_ms":20}}
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
   here — the connector's userspace `ulimit` fallback (`AXIS_ULIMIT_NPROC`)
   covers it.
2. **AXIS built from source** (`qedawkins/axis`, Rust) into `$HALO_TOOLS/bin` by
   `platforms/halo/setup.sh`; the seccomp launcher refuses a group-writable install path,
   so the whole ancestry is 755.
3. **Audit sink is a local SQLite DB** (`AUDIT_DB`, default `$HOME/axis-audit.db`)
   for a fully self-contained run — both planes write into the same file, so
   enforcement and the audit record are entirely local with no network
   dependency.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
