<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side Router Test: **semantic routing** on the inference-plane proxy

Extends [`../lemonade_test/`](../lemonade_test/) (which
proved the transparent inference-plane telemetry proxy → real Splunk `index=axis`)
by adding the **vLLM Semantic Router** to that proxy. The router does difficulty-based
per-prompt routing: easy → local free model, hard → frontier Claude. It runs
entirely on the deskside, integrated into the proxy, with an A/B test, and the Splunk
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
     │  1. DefenseClaw /api/v1/inspect/request        (prompt guardrail, observe)
     │  2. router.route(prompt):
     │       POST semantic-router /api/v1/classify/intent {text}      (NO inference)
     │       -> recommended_model, routing_decision, matched_signals.complexity
     │       tier = claude-* ? frontier : local            (fail-OPEN -> local)
     │  3a. tier=local     -> forward BYTE-FOR-BYTE ─────►  Lemonade :13305 (Qwen3-8B)
     │  3b. tier=frontier  -> swap model + auth header ──►  AMD LLM Gateway (claude-opus-4.8)
     │        (only when a frontier key is configured; else fail-safe to local)
     │  4. DefenseClaw /api/v1/inspect/response        (completion guardrail, observe)
     │  5. emit llm.request  (now with a `routing` block) ─► REAL Splunk index=axis
     ▼                                                        sourcetype axis:llm
   response streamed back + additive x-lemon-* routing headers (body untouched)
```

The toggle `LEMON_ROUTER=on|off` lives on the **proxy**. The runner starts a
baseline proxy (off) and a router-on proxy (on) and runs the A/B against both.

## Two tiers

| Tier | Backend | Cost | Route |
|------|---------|------|-------|
| local | Lemonade `Qwen3-8B-GGUF` on CPU (`:13305`) | free | simple / factual prompts |
| frontier | AMD LLM Gateway `claude-opus-4.8` (Anthropic-compatible) | paid | hard reasoning / proofs / planning |

Both speak the Anthropic API, so escalation is just a different upstream base +
auth header (`Ocp-Apim-Subscription-Key`) + a `model` rewrite in the body. The
frontier tier is configurable (env) — set `FRONTIER_UPSTREAM=https://api.anthropic.com`,
`FRONTIER_AUTH_HEADER=x-api-key`, `FRONTIER_MODEL=claude-haiku-4-5-20251001` for
Anthropic direct.

## Fail-open, always

A router hiccup must never take inference down (same principle as the DefenseClaw
inference client). Router unreachable / slow / erroring → the request stays on the
**local** tier and inference continues. When the router picks frontier but no
frontier key is configured, the proxy records the **decision** but serves local
(fail-safe).

## What it proves

1. **transparent + consult-only** — the proxy still forwards byte-for-byte; the
   router is only asked for a decision, never in the data path.
2. **baseline (router off)** — every prompt stays local; `llm.request` with
   `routing.enabled=false` confirmed in `index=axis`.
3. **router-on** — simple prompts stay local, hard prompts get a **frontier
   decision** (`routing.selected_model=claude-*`) and, with a key, actually
   escalate (`routing.tier=frontier`). Routing correctness is read from the
   proxy's `x-lemon-*` response headers **and** the Splunk `routing` block.
4. **Claude Code through the router-on proxy** (best-effort) — its inference lands
   `llm.request` events carrying the routing block under session `cc-router`.

## New telemetry: the `routing` block

Every `llm.request` now carries (metadata only, no prompt/completion text):

```json
"routing": {
  "enabled": true, "reachable": true,
  "decision": "frontier-reasoning",
  "complexity": "needs_reasoning:hard",
  "selected_model": "claude-opus-4.8",
  "tier": "frontier",
  "upstream": "https://<llm-gateway>/Anthropic",
  "classify_ms": 42
}
```

`null` on a plain passthrough build (router disabled and never consulted). See
[`../../stack/TELEMETRY_CONTRACT.md`](../../stack/TELEMETRY_CONTRACT.md)
§8.

## Reuse (no duplication)

- `../../stack/lemonade_proxy/` — the proxy (now with `src/router.js`) + unit tests.
- `../../stack/lemonade/run_lemonade.sh` — local Lemonade (local tier).
- `../../stack/defenseclaw/run_gateway.sh` — the real DefenseClaw gateway.
- the semantic-router build — provides `~/repos/semantic-router/bin/router` + models (reused here).
- `../../stack/splunk/install_splunk.sh` + `query_splunk.sh` — real Splunk + read-back.

## Layout

```
router_test/
  README.md  SETUP.md  RESULTS.md
  config.yaml                 semantic-router config (client-side model names)
  run_router_telemetry.sh     end-to-end runner (the main new code)
  router_ab_probe.py          Anthropic /v1/messages A/B driver (reads x-lemon-*)
  test_router_ab_probe.py     pure-logic unit tests for the probe
  claude_job.sh               Claude Code with ANTHROPIC_BASE_URL -> router-on proxy
  artifacts/                  SUMMARY.txt, ab_results.json, events.jsonl, splunk_query.txt, *.log
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd router_test
export PATH=$HOME/.local/go/bin:$PATH   # DefenseClaw's Go check
GATEWAY_KEY=<amd-gateway-key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_router_telemetry.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
