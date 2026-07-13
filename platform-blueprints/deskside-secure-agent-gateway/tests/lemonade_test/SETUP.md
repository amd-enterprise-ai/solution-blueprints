<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — client-side Lemonade (inference-plane) telemetry test

Reference target: a Strix Halo deskside with `lemonade`, the DefenseClaw
gateway, and the real Splunk.

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Node ≥18 | proxy + unit tests | `node --version` |
| local Lemonade | inference backend (Qwen3-8B on CPU) | `curl -sf 127.0.0.1:13305/api/v1/health` |
| Go on PATH | DefenseClaw `run_gateway.sh` reuses its prebuilt binary | `command -v go` |
| real Splunk | audit sink | reuse the local `~/splunk`, or `SPLUNK_URL`/`SPLUNK_TGZ` |
| `claude` | optional cross-check (Stage 6) | `command -v claude` |

The sibling tree `../../stack` must be present alongside this folder — this test
reuses it by relative path.

> **Go gotcha:** `run_gateway.sh` bails with "Go toolchain required" *before* the
> block that reuses its prebuilt binary. On the deskside put the user-local
> Go on PATH first: `export PATH=$HOME/.local/go/bin:$PATH`.

## One-shot end-to-end

```bash
cd lemonade_test
export PATH=$HOME/.local/go/bin:$PATH   # so DefenseClaw's Go check passes
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_lemonade_telemetry.sh
```

If a real Splunk is already running and the creds authenticate, the runner
**reuses it** and skips the install. Pass
`SPLUNK_PASS=<SPLUNK_PASS>` and `HEC_TOKEN=<HEC_TOKEN>`
so the proxy and the search-verification use the instance's real token.

Stages (pass/fail → `artifacts/SUMMARY.txt`):

0. **preconditions** — node; run the proxy's 22 unit tests.
1. **real Splunk** — reuse-or-install; HEC + mgmt/search health.
2. **DefenseClaw gateway** — `:18970`; token minted + propagated to the proxy.
3. **Lemonade** — reuse-or-boot `Qwen3-8B-GGUF` on CPU via
   `../../stack/lemonade/run_lemonade.sh`; Anthropic endpoint healthy.
4. **proxy** — start `lemonade_proxy` in front of Lemonade (session `lemon-probe`).
5. **deterministic probe (HARD)** — `curl` a real `/v1/messages` through the proxy;
   assert a real completion + `llm.request(decision=allow)` for session
   `lemon-probe` **confirmed in `index=axis`** (sourcetype `axis:llm`) via the
   search API, carrying a DefenseClaw prompt verdict.
6. **Claude Code (best-effort)** — point Claude Code's `ANTHROPIC_BASE_URL` at a
   second proxy (session `cc-lemon`); confirm an `llm.request` in Splunk. Reported
   `cc=ok`, else `cc=skip` (weak local model can't always carry Claude Code's loop).
7. **summary** — `artifacts/SUMMARY.txt` + the search read-back into
   `artifacts/splunk_query.txt`.

Useful env overrides: `LEMON_MODEL` (default `Qwen3-8B-GGUF`), `LEMONADE_PORT`
(default `13305`), `PROXY_PORT`/`PROXY_PORT2` (default `13399`/`13398`),
`DC_PORT`, `RUN_CC=0` (skip the Claude Code stage), `SPLUNK_PASS`, `HEC_TOKEN`,
`SPLUNK_URL`/`SPLUNK_TGZ` (install fresh).

## What to look for in `artifacts/`

- `SUMMARY.txt` — `N passed / M failed` + up flags + `cc=ok/skip`.
- `proxy_probe.json` — the deterministic completion streamed back through the proxy.
- `events.jsonl` — the local copy of `llm.*` events the proxy built.
- `splunk_query.txt` — the events **as Splunk indexed them** (search API), the real proof.
- `proxy_probe.log` / `proxy_cc.log` — the proxy's own stderr (listen line + verdicts).

## Troubleshooting

- **HEC POST silently dropped** — Node's `fetch` rejects Splunk's self-signed
  cert; the runner sets `NODE_TLS_REJECT_UNAUTHORIZED=0`.
- **`{"error":"unauthorized"}` from DefenseClaw** — a stale gateway on `DC_PORT`;
  the runner kills it before starting. The proxy fails **open** on the inference
  plane, so a down gateway still lets inference through (verdict `reachable=false`).
- **search returns 0 rows briefly** — indexing lag; the runner polls ~60s. Keep
  `/` above ~6 GB free (Splunk `minFreeSpace` silently halts indexing+search).
- **Stage 6 SKIP** — Claude Code expects a capable model; the local 8B may return
  malformed responses that stall its loop. The Stage 5 deterministic probe still
  HARD-proves the proxy → Splunk path. Set `RUN_CC=0` to skip it entirely.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
