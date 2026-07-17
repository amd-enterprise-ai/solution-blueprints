<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side Lemonade Test: **inference-plane** telemetry to the SQLite audit DB

Proves the client-side governance story extends from the **tool plane** (the
`axis_mcp_connector` → AXIS → SQLite `axis.toolcall` events) to the
**inference plane**: every LLM request made by the agent host is audited to the
**same local SQLite audit DB** as an `llm.request` event.

The new component is a **transparent telemetry proxy** in front of the local
Lemonade server. No Lemonade source is modified — the agent host just points its
`ANTHROPIC_BASE_URL` at the proxy instead of directly at Lemonade.

```
   Claude Code (or any Anthropic client)
     │ ANTHROPIC_BASE_URL -> proxy
     ▼
   lemonade_proxy (Node, stack/lemonade_proxy)
     │  1. forward /v1/messages  BYTE-FOR-BYTE  ─────────────►  Lemonade :13305
     │  2. emit llm.request ──────────────────►  SQLite audit DB (AUDIT_DB)   (Qwen3-8B, CPU)
     ▼
   response streamed back to the client unchanged
```

## Two planes, one audit DB

| Plane | Producer | Event |
|-------|----------|-------|
| tool  | `axis_mcp_connector` | `axis.toolcall` |
| inference | `lemonade_proxy` | `llm.request` |

Both carry the same `identity{session,user,tenant,device_id}` block and write to the
same SQLite `AUDIT_DB` (WAL mode, so the two writers coexist), so a single agent
session's tool calls and LLM calls correlate by `identity.session`.

## Why a proxy (not a Lemonade patch)

Lemonade is upstream AMD code; patching it to emit audit events would rot against
every release. A transparent proxy keeps the telemetry entirely on the client
side, reuses the connector's exact SQLite sink pattern, and works for
**any** Anthropic-speaking host (Claude Code, gaia, curl) unchanged. The proxy
never alters the bytes it forwards — parsing (model/prompt/token usage) is
best-effort telemetry, never on the data path.

**Privacy:** the event records metadata only — model, timing, token counts, and
prompt/response **char counts**. It never stores the raw prompt or completion
text (mirrors the connector recording exit/duration, not stdout). This plane has
no guardrail integration — the AXIS sandbox is the sole enforcement layer, and
the proxy only observes and records.

## What it proves

1. **proxy is transparent** — `/v1/messages` (JSON and SSE) is forwarded
   byte-for-byte; the client sees an unmodified Lemonade response.
2. **deterministic HARD proof** — a real `/v1/messages` call through the proxy
   produces an `llm.request(decision=allow)` event **read back out of the SQLite
   audit DB with SQL**. Model-independent.
3. **Claude Code through the proxy** (best-effort) — Claude Code's own inference,
   pointed at the proxy, lands its `llm.request` events in the SQLite audit DB
   under session `cc-lemon`. Reported SKIP if the local 8B can't carry Claude
   Code's loop (the deterministic stage still HARD-proves the plane).

## Reuse (no duplication)

- `../../stack/lemonade_proxy/` — the proxy + its unit tests (new).
- `../../stack/lemonade/run_lemonade.sh` — local Lemonade on CPU.
- `../lib/audit_db.sh` — shared SQLite audit-DB read-back helpers.

## Layout

```
lemonade_test/
  README.md  SETUP.md  RESULTS.md
  run_lemonade_telemetry.sh   end-to-end runner (the main new code)
  claude_job.sh               Claude Code with ANTHROPIC_BASE_URL -> proxy
  artifacts/                  SUMMARY.txt, audit.db, proxy_*.log
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd lemonade_test
  bash run_lemonade_telemetry.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
