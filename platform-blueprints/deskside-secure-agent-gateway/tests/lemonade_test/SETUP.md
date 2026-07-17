<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side Lemonade (inference-plane) telemetry test

Reference target: a Strix Halo deskside with `lemonade`. Audit is a local SQLite DB.

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Node ≥18 | proxy + unit tests | `node --version` |
| local Lemonade | inference backend (Qwen3-8B on CPU) | `curl -sf 127.0.0.1:13305/api/v1/health` |
| `claude` | optional cross-check (Stage 6) | `command -v claude` |

The sibling tree `../../stack` must be present alongside this folder — this test
reuses it by relative path. The audit sink is a local SQLite DB (`AUDIT_DB`, default
`artifacts/audit.db`); no external audit service is required.

## One-shot end-to-end

```bash
cd lemonade_test
  bash run_lemonade_telemetry.sh
```

The proxy writes every `llm.request` to the SQLite audit DB. The runner starts from a
clean `AUDIT_DB` each run so the checks assert on this run's events.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node; run the proxy's unit tests.
3. **Lemonade** — reuse-or-boot `Qwen3-8B-GGUF` on CPU via
   `../../stack/lemonade/run_lemonade.sh`; Anthropic endpoint healthy.
4. **proxy** — start `lemonade_proxy` in front of Lemonade (session `lemon-probe`).
5. **deterministic probe (HARD)** — `curl` a real `/v1/messages` through the proxy;
   assert a real completion + `llm.request(decision=allow)` for session
   `lemon-probe` **confirmed in the SQLite audit DB** by reading it back with SQL.
6. **Claude Code (best-effort)** — point Claude Code's `ANTHROPIC_BASE_URL` at a
   second proxy (session `cc-lemon`); confirm an `llm.request` in the SQLite audit DB.
   Reported `cc=ok`, else `cc=skip` (weak local model can't always carry Claude Code's loop).
7. **summary** — `artifacts/SUMMARY.txt` (SQLite event count).

Useful env overrides: `AUDIT_DB` (SQLite path), `LEMON_MODEL` (default `Qwen3-8B-GGUF`),
`LEMONADE_PORT` (default `13305`), `PROXY_PORT`/`PROXY_PORT2` (default `13399`/`13398`),
`RUN_CC=0` (skip the Claude Code stage).

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + up flags + `cc=ok/skip`.
- `proxy_probe.json` — the deterministic completion streamed back through the proxy.
- `audit.db` — the SQLite audit DB; read the `llm.*` events back with SQL, e.g.
  `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'` — the real proof.
- `proxy_probe.log` / `proxy_cc.log` — the proxy's own stderr (listen line + events).

## Troubleshooting

- **audit DB empty / checks can't confirm an event** — the proxy writes to `AUDIT_DB`
  (default `artifacts/audit.db`); make sure that path is writable and that the same
  `AUDIT_DB` is exported to the proxy and the read-back helper. The SQLite sink is
  fail-soft, so a bad path degrades to a no-op instead of crashing the proxy.
- **Stage 6 SKIP** — Claude Code expects a capable model; the local 8B may return
  malformed responses that stall its loop. The Stage 5 deterministic probe still
  HARD-proves the proxy → SQLite path. Set `RUN_CC=0` to skip it entirely.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
