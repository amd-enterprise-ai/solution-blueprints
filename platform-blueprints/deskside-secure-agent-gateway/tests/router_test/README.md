<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side Router Test: **semantic routing** on the inference-plane proxy

Extends [`../lemonade_test/`](../lemonade_test/) (which
proved the transparent inference-plane telemetry proxy → the SQLite audit DB)
by adding the **vLLM Semantic Router** to that proxy. The router does difficulty-based
per-prompt routing: easy → local free model, hard → frontier Claude. It runs
entirely on the deskside, integrated into the proxy, with an A/B test, and the audit
telemetry is extended to carry the routing decision.

## The consult-only integration (no inline data plane)

There is no orchestrator and no rack control plane — everything runs on one
machine. The proxy stays a transparent byte-for-byte data path and only
**consults** the router: the semantic-router binary exposes a standalone classify
API that returns a routing decision for a prompt **without running any inference
and without sitting in the data path**.

```
   Claude Code (or any Anthropic client)
     │ ANTHROPIC_BASE_URL -> proxy
     ▼
   lemonade_proxy  (LEMON_ROUTER=on)
     │  1. router.route(prompt):
     │       POST semantic-router /api/v1/classify/intent {text}      (NO inference)
     │       -> recommended_model, routing_decision, matched_signals.complexity
     │       tier = claude-* ? frontier : local            (fail-OPEN -> local)
     │  2a. tier=local     -> forward BYTE-FOR-BYTE ─────►  Lemonade :13305 (Qwen3-8B)
     │  2b. tier=frontier  -> swap model + auth header ──►  Anthropic direct (claude-opus-4-8) [or a gateway]
     │        (only when a frontier key is configured; else fail-safe to local)
     │  3. emit llm.request  (now with a `routing` block) ─► SQLite audit DB (AUDIT_DB)
     ▼
   response streamed back + additive x-lemon-* routing headers (body untouched)
```

The toggle `LEMON_ROUTER=on|off` lives on the **proxy**. The runner starts a
baseline proxy (off) and a router-on proxy (on) and runs the A/B against both.

## Two tiers

| Tier | Backend | Cost | Route |
|------|---------|------|-------|
| local | Lemonade `Qwen3-8B-GGUF` on CPU (`:13305`) | free | simple / factual prompts |
| frontier | Anthropic `claude-opus-4-8` (default; or a gateway) | paid | hard reasoning / proofs / planning |

Both speak the Anthropic API, so escalation is just a different upstream base +
auth header + a `model` rewrite in the body. The frontier tier defaults to
**Anthropic direct** (`https://api.anthropic.com`, `x-api-key`, `claude-opus-4-8`);
point it at a gateway by overriding `FRONTIER_UPSTREAM` + `FRONTIER_AUTH_HEADER`
(or the `GATEWAY_KEY` alias).

## Fail-open, always

A router hiccup must never take inference down. Router unreachable / slow / erroring
→ the request stays on the **local** tier and inference continues. When the router
picks frontier but no frontier key is configured, the proxy records the **decision**
but serves local (fail-safe).

## What it proves

1. **transparent + consult-only** — the proxy still forwards byte-for-byte; the
   router is only asked for a decision, never in the data path.
2. **baseline (router off)** — every prompt stays local; `llm.request` with
   `routing.enabled=false` confirmed in the SQLite audit DB.
3. **router-on** — simple prompts stay local, hard prompts get a **frontier
   decision** (`routing.selected_model=claude-*`) and, with a key, actually
   escalate (`routing.tier=frontier`). Routing correctness is read from the
   proxy's `x-lemon-*` response headers **and** the audit DB's `routing` block.
4. **Claude Code through the router-on proxy** (best-effort) — its inference lands
   `llm.request` events carrying the routing block under session `cc-router`.

## New telemetry: the `routing` block

Every `llm.request` now carries (metadata only, no prompt/completion text):

```json
"routing": {
  "enabled": true, "reachable": true,
  "decision": "frontier-reasoning",
  "complexity": "needs_reasoning:hard",
  "selected_model": "claude-opus-4-8",
  "tier": "frontier",
  "upstream": "https://api.anthropic.com",
  "classify_ms": 42
}
```

`null` on a plain passthrough build (router disabled and never consulted). See
[`../../stack/TELEMETRY_CONTRACT.md`](../../stack/TELEMETRY_CONTRACT.md)
§8.

## Reuse (no duplication)

- `../../stack/lemonade_proxy/` — the proxy (now with `src/router.js`) + unit tests.
- `../../stack/lemonade/run_lemonade.sh` — local Lemonade (local tier).
- the semantic-router build — provides `~/repos/semantic-router/bin/router` + models (reused here).
- `../lib/audit_db.sh` — shared SQLite audit-DB read-back helpers.

## Layout

```
router_test/
  README.md  RESULTS.md
  config.yaml                 semantic-router config (client-side model names)
  run_router_telemetry.sh     end-to-end runner (the main new code)
  router_ab_probe.py          Anthropic /v1/messages A/B driver (reads x-lemon-*)
  test_router_ab_probe.py     pure-logic unit tests for the probe
  claude_job.sh               Claude Code with ANTHROPIC_BASE_URL -> router-on proxy
  artifacts/                  SUMMARY.txt, ab_results.json, audit.db, *.log
```

## Setup & run

### Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Node 22 + npm | proxy + unit tests | `node --version && npm --version` |
| local Lemonade | local tier (Qwen3-8B on CPU) | `curl -sf 127.0.0.1:13305/api/v1/health` |
| `~/repos/semantic-router/bin/router` | classify API (consult-only) | built by the semantic-router build step |
| frontier key (optional) | actually escalate hard prompts | `ANTHROPIC_API_KEY` (or `GATEWAY_KEY`/`FRONTIER_AUTH_KEY`) |
| `claude` (optional) | cross-check (Stage 8) | `command -v claude` |

The sibling tree `../../stack` must be present alongside this folder (reused by relative path),
along with the prebuilt semantic-router at `~/repos/semantic-router`. The audit sink is a local
SQLite DB (`AUDIT_DB`, default `artifacts/audit.db`); no external audit service is required.

> **Router binary:** the runner **reuses** `~/repos/semantic-router/bin/router` and the downloaded
> candle embedding models (built by the semantic-router build step). If `bin/router` is absent the
> runner FAILs Stage 4 with a pointer to that build. The candle `.so`s are loaded via
> `LD_LIBRARY_PATH` (the runner sets it to the 3 `*-binding/target/release` dirs).

> **Port note:** the classify API's default `:8088` can collide with other services on this
> machine. The runner uses `ROUTER_API_PORT=18088` instead and points the proxy at it via
> `SEMANTIC_ROUTER_URL`.

### One-shot end-to-end

Default frontier is **Anthropic direct** — just bring an `ANTHROPIC_API_KEY`:

```bash
cd router_test
ANTHROPIC_API_KEY=<key> bash run_router_telemetry.sh
```

Lemonade and the classify API are each reuse-or-boot. The proxy writes every `llm.request` (routing
block included) to the SQLite audit DB; the runner starts from a clean `AUDIT_DB` each run.
Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node; proxy unit tests; the probe's unit tests.
3. **Lemonade** — reuse-or-boot `Qwen3-8B-GGUF` on CPU (local tier).
4. **semantic-router classify API** — reuse-or-start `bin/router` on `:18088`; readiness = a
   `POST /api/v1/classify/intent` returns 200. A sample classification is saved to
   `artifacts/classify_sample.json`.
5. **frontier preflight** — if a key is set, a real `/v1/messages` to the frontier proves the tier;
   else frontier is marked unavailable (routing still classifies).
6. **baseline** (session `router-baseline`, `LEMON_ROUTER=off`) — probe all prompts; assert every
   one stayed local + `routing.enabled=false` in the SQLite audit DB.
7. **router-on** (session `router-on`, `LEMON_ROUTER=on`) — same prompts; assert per the `x-lemon-*`
   headers **and** the audit DB's `routing` block: simple → local, hard → frontier decision
   (`routing.selected_model=claude-*`), and — with a key — an actual `routing.tier=frontier`
   escalation. Routing correctness reported.
8. **Claude Code (best-effort)** — router-on proxy (session `cc-router`); confirm an `llm.request`
   with a routing block in the SQLite audit DB. `cc=ok|skip`.
9. **summary** — `artifacts/SUMMARY.txt` (SQLite event count).

Useful env overrides: `AUDIT_DB` (SQLite path), `LEMON_MODEL` (default `Qwen3-8B-GGUF`),
`LEMONADE_PORT` (`13305`), `ROUTER_API_PORT` (`18088`), `ROUTER_REPO_DIR` (`~/repos/semantic-router`),
`PROXY_BASELINE_PORT`/`PROXY_ROUTER_PORT`/`PROXY_CC_PORT` (`13399`/`13398`/`13397`),
`FRONTIER_UPSTREAM`/`FRONTIER_MODEL`/`FRONTIER_AUTH_HEADER`/`FRONTIER_AUTH_KEY`,
`FRONTIER_EXTRA_HEADERS` (JSON — extra headers some gateways require on frontier calls; see below),
`RUN_CC=0`.

The default uses `FRONTIER_MODEL=claude-opus-4-8` (the strong tier for hard prompts). The
`anthropic-version` header Anthropic requires is already supplied by the probe / Claude Code and
forwarded by the proxy, so nothing extra is needed for Anthropic direct.

#### Gateway frontier (alternative)

If you have access to an Anthropic-compatible **gateway**, point the frontier tier at it instead —
set the gateway URL + its auth header and pass the key:

```bash
FRONTIER_UPSTREAM=https://your-gateway/Anthropic \
FRONTIER_AUTH_HEADER=Ocp-Apim-Subscription-Key \
GATEWAY_KEY=<gateway-key> bash run_router_telemetry.sh
```

Some gateway accounts also require **extra headers** on frontier calls (this depends on the
subscription/account, **not** the blueprint). If escalation returns 4xx (or `routing.tier=frontier`
never succeeds despite a valid key), inject them via `FRONTIER_EXTRA_HEADERS`:

```bash
FRONTIER_UPSTREAM=https://your-gateway/Anthropic \
FRONTIER_AUTH_HEADER=Ocp-Apim-Subscription-Key \
GATEWAY_KEY=<gateway-key> \
FRONTIER_EXTRA_HEADERS='{"anthropic-version":"vertex-2023-10-16","user":"<username>"}' \
  bash run_router_telemetry.sh
```

Some accounts need no extra headers at all — check what your gateway account requires.

### What to look for in `artifacts/`

- `SUMMARY.txt` — up flags + `routing_correct=N/M` + `frontier_ready` + `cc=ok/skip` + `pass/fail`.
- `ab_results.json` / `ab_run.txt` — the A/B: per-prompt tier, latency, cost + deltas.
- `classify_sample.json` — a raw classify response (proves the API shape).
- `frontier_preflight.json` — the frontier completion (when a key is set).
- `audit.db` — the SQLite audit DB; read the `llm.*` events (routing block included) back with SQL,
  e.g. `sqlite3 artifacts/audit.db 'SELECT data FROM events ORDER BY id;'`.
- `proxy_baseline.log` / `proxy_routeron.log` / `router.log` — service stderr.

### Troubleshooting

- **Stage 4 FAIL / classify never 200** — `bin/router` missing or the candle `.so`s / models aren't
  present; run the semantic-router build step first. Embedding-model load can take ~30–60s on first
  start (the runner polls ~180s).
- **`routing.tier=frontier` never appears** — either no frontier key on the node, or the gateway
  rejected the call (4xx) because your account needs extra headers. The decision is still proven via
  `routing.selected_model=claude-*`; set a key to see real escalation, and if a gateway 4xxs, add
  `FRONTIER_EXTRA_HEADERS` (see "Gateway frontier (alternative)" above).
- **audit DB empty / checks can't confirm an event** — the proxy writes to `AUDIT_DB` (default
  `artifacts/audit.db`); make sure that path is writable and shared between the proxy and the
  read-back helper.
- **Stage 8 SKIP** — the local 8B may stall Claude Code's loop; the deterministic A/B stages still
  HARD-prove the plane. Set `RUN_CC=0` to skip entirely.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
