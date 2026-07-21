<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side semantic-router (inference-plane) A/B test

Run on a Strix Halo deskside @ 2026-07-01T11:44:20Z (node v24.18.0).
Artifacts: `artifacts/node_run/`.

## Local (pre-flight, laptop)

- Proxy unit tests: **37/37** (`cd ../../stack/lemonade_proxy && node --test`)
  — plus `router.test.js`, server routing tests, and `cross_plane_session.test.js`.
- A/B probe unit tests: **12/12** (`python3 -m pytest test_router_ab_probe.py`).
  (Skipped on the node — pytest not installed there; verified off-node.)

## Node run (reference node)

```
router_test run @ 2026-07-01T11:44:20Z
host=<halo-host> node=v24.18.0
inference: proxy -> Lemonade Qwen3-8B-GGUF (local :13305) | frontier claude-opus-4.8 @ https://<llm-gateway>/Anthropic
router: classify API :18088 (consult-only); toggle=LEMON_ROUTER
audit: SQLite audit DB (AUDIT_DB) with routing block
lemonade_up=1 router_up=1 frontier_ready=0
routing_correct=7/7
pass=17 fail=0
cc=ok
```

**Result: 17 passed, 0 failed.** No frontier key on the node (`frontier_ready=0`),
so hard prompts prove the **frontier decision** (`routing.selected_model=claude-opus-4.8`)
and fail safe to local (`routing.tier=local`) rather than actually escalating —
the intended behavior. Set `GATEWAY_KEY` to see real `routing.tier=frontier`.

### Checklist

- [x] Stage 0 — proxy 37/37 (probe unit tests verified off-node; pytest absent on node)
- [x] Stage 3 — Lemonade local tier `:13305`
- [x] Stage 4 — semantic-router classify API `:18088`
- [x] Stage 5 — frontier preflight (`frontier_ready=0` — no key supplied)
- [x] Stage 6 — baseline all-local + `routing.enabled=false` confirmed in the SQLite audit DB
- [x] Stage 7 — router-on: simple→local, hard→frontier **decision**
      (`routing.selected_model=claude-opus-4.8`) confirmed in the SQLite audit DB; `routing.tier=local`
      (fail-safe, no key); `routing_correct=7/7`
- [x] Stage 8 — Claude Code through the router-on proxy (`cc=ok`)
- [x] Stage 9 — SQLite audit DB read-back attached

### A/B summary

_from `ab_run.txt` — baseline vs router-on cost/task + avg latency._

| pass | ok | avg latency | cost/task | all-local |
|------|----|-------------|-----------|-----------|
| baseline | 7/7 | 4.24s | $0.000000 | true |
| router-on | 7/7 | 3.76s | $0.000000 | true (fail-safe, no key) |

routing correctness (router-on): **7/7** prompts to the expected tier
(4 simple → `lemonade-local` / `needs_reasoning:easy`; 3 reasoning →
`claude-opus-4.8` frontier decision / `needs_reasoning:hard|medium`).

Cost/task is $0 on both passes because no frontier key was present, so every
served request stayed on the free local tier. The routing **decision** is still
recorded per prompt in the audit DB's `routing` block.

### Recorded `routing` block (frontier decision, from the SQLite audit DB)

```json
"routing": {
  "enabled": true, "reachable": true,
  "decision": "frontier-reasoning",
  "complexity": "needs_reasoning:hard",
  "selected_model": "claude-opus-4.8",
  "tier": "local",
  "upstream": "http://127.0.0.1:13305",
  "classify_ms": 437
}
```

`tier=local` with `selected_model=claude-opus-4.8` is the fail-safe path: the
router **decided** frontier, but with no frontier key the proxy served local and
recorded the decision. With a key, `tier` becomes `frontier` and `upstream`
becomes the Anthropic-compatible gateway.

### Notes

- The router binary always starts a gRPC ExtProc server (`:50051`) and a metrics
  server (`:9190`) even in consult-only use; a pre-existing router instance held
  `:50051`, so the runner now launches with `-port=50151 -metrics-port=19190` to
  avoid a fatal bind clash.
- Newer router builds run a `huggingface-cli` model check at startup; the runner
  reuses a venv's `huggingface-cli` on PATH if the base env lacks it.
- `classify_sample.json` is empty this run (the Stage-4 sample curl fired before
  the embedding runtime finished warming); classify was fully healthy during the
  probe — see the 7/7 correctness and the `classify_ms` in every `routing` block.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
