<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side semantic-router (inference-plane) A/B test

Reference target: a Strix Halo deskside with `lemonade` and the prebuilt
semantic-router. Audit is a local SQLite DB.

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Node ≥18 | proxy + unit tests | `node --version` |
| local Lemonade | local tier (Qwen3-8B on CPU) | `curl -sf 127.0.0.1:13305/api/v1/health` |
| `~/repos/semantic-router/bin/router` | classify API (consult-only) | built by the semantic-router build step |
| frontier key (optional) | actually escalate hard prompts | `GATEWAY_KEY` (or `ANTHROPIC_API_KEY`/`FRONTIER_AUTH_KEY`) |
| `claude` (optional) | cross-check (Stage 8) | `command -v claude` |

The sibling tree `../../stack` must be present alongside this folder — this test
reuses it by relative path — along with the prebuilt semantic-router at
`~/repos/semantic-router`. The audit sink is a local SQLite DB (`AUDIT_DB`, default
`artifacts/audit.db`); no external audit service is required.

> **Router binary:** the runner **reuses** `~/repos/semantic-router/bin/router`
> and the downloaded candle embedding models (built by the semantic-router build
> step). If `bin/router` is absent the runner FAILs Stage 4 with a pointer to that
> build. The candle `.so`s are loaded via `LD_LIBRARY_PATH` (the runner sets it to
> the 3 `*-binding/target/release` dirs).

> **Port note:** the classify API's default `:8088` can collide with other
> services on this machine. The runner uses `ROUTER_API_PORT=18088` instead and
> points the proxy at it via `SEMANTIC_ROUTER_URL`.

## One-shot end-to-end

```bash
cd router_test
GATEWAY_KEY=<amd-gateway-key> \
  bash run_router_telemetry.sh
```

Lemonade and the classify API are each reuse-or-boot. The proxy writes every
`llm.request` (routing block included) to the SQLite audit DB; the runner starts
from a clean `AUDIT_DB` each run.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node; proxy unit tests; the probe's unit tests.
3. **Lemonade** — reuse-or-boot `Qwen3-8B-GGUF` on CPU (local tier).
4. **semantic-router classify API** — reuse-or-start `bin/router` on `:18088`;
   readiness = a `POST /api/v1/classify/intent` returns 200. A sample
   classification is saved to `artifacts/classify_sample.json`.
5. **frontier preflight** — if a key is set, a real `/v1/messages` to the frontier
   proves the tier; else frontier is marked unavailable (routing still classifies).
6. **baseline** (session `router-baseline`, `LEMON_ROUTER=off`) — probe all
   prompts; assert every one stayed local + `routing.enabled=false` in the SQLite audit DB.
7. **router-on** (session `router-on`, `LEMON_ROUTER=on`) — same prompts; assert
   per the `x-lemon-*` headers **and** the audit DB's `routing` block: simple → local,
   hard → frontier decision (`routing.selected_model=claude-*`), and — with a key
   — an actual `routing.tier=frontier` escalation. Routing correctness reported.
8. **Claude Code (best-effort)** — router-on proxy (session `cc-router`); confirm
   an `llm.request` with a routing block in the SQLite audit DB. `cc=ok|skip`.
9. **summary** — `artifacts/SUMMARY.txt` (SQLite event count).

Useful env overrides: `AUDIT_DB` (SQLite path), `LEMON_MODEL` (default `Qwen3-8B-GGUF`),
`LEMONADE_PORT` (`13305`), `ROUTER_API_PORT` (`18088`), `ROUTER_REPO_DIR`
(`~/repos/semantic-router`),
`PROXY_BASELINE_PORT`/`PROXY_ROUTER_PORT`/`PROXY_CC_PORT` (`13399`/`13398`/`13397`),
`FRONTIER_UPSTREAM`/`FRONTIER_MODEL`/`FRONTIER_AUTH_HEADER`/`FRONTIER_AUTH_KEY`,
`FRONTIER_EXTRA_HEADERS` (JSON, e.g. `{"anthropic-version":"2023-06-01"}` for
Anthropic direct), `RUN_CC=0`.

### Anthropic-direct frontier (alternative)

```bash
FRONTIER_UPSTREAM=https://api.anthropic.com \
FRONTIER_AUTH_HEADER=x-api-key \
FRONTIER_MODEL=claude-haiku-4-5-20251001 \
FRONTIER_EXTRA_HEADERS='{"anthropic-version":"2023-06-01"}' \
ANTHROPIC_API_KEY=<key> bash run_router_telemetry.sh
```

## What to look for in `artifacts/`

- `SUMMARY.txt` — up flags + `routing_correct=N/M` + `frontier_ready` + `cc=ok/skip` + `pass/fail`.
- `ab_results.json` / `ab_run.txt` — the A/B: per-prompt tier, latency, cost + deltas.
- `classify_sample.json` — a raw classify response (proves the API shape).
- `frontier_preflight.json` — the frontier completion (when a key is set).
- `audit.db` — the SQLite audit DB; read the `llm.*` events (routing block included)
  back with SQL, e.g. `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'`.
- `proxy_baseline.log` / `proxy_routeron.log` / `router.log` — service stderr.

## Troubleshooting

- **Stage 4 FAIL / classify never 200** — `bin/router` missing or the candle
  `.so`s / models aren't present; run the semantic-router build step first.
  Embedding-model load can take ~30–60s on first start (the runner polls ~180s).
- **`routing.tier=frontier` never appears** — no frontier key on the node. The
  decision is still proven via `routing.selected_model=claude-*`; set `GATEWAY_KEY`
  to see real escalation.
- **audit DB empty / checks can't confirm an event** — the proxy writes to `AUDIT_DB`
  (default `artifacts/audit.db`); make sure that path is writable and shared between
  the proxy and the read-back helper.
- **Stage 8 SKIP** — the local 8B may stall Claude Code's loop; the deterministic
  A/B stages still HARD-prove the plane. Set `RUN_CC=0` to skip entirely.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
