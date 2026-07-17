<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side Lemonade Test: **inference-plane** telemetry to real Splunk

Proves the client-side governance story extends from the **tool plane** (the
`axis_mcp_connector` → DefenseClaw → AXIS → Splunk `axis.toolcall` events) to the
**inference plane**: every LLM request made by the agent host is audited to the
**same real Splunk `index=axis`** as an `llm.request` event.

The new component is a **transparent telemetry proxy** in front of the local
Lemonade server. No Lemonade source is modified — the agent host just points its
`ANTHROPIC_BASE_URL` at the proxy instead of directly at Lemonade.

```
   Claude Code (or any Anthropic client)
     │ ANTHROPIC_BASE_URL -> proxy
     ▼
   lemonade_proxy (Node, stack/lemonade_proxy)
     │  1. DefenseClaw /api/v1/inspect/request   (prompt guardrail, observe)
     │  2. forward /v1/messages  BYTE-FOR-BYTE  ─────────────►  Lemonade :13305
     │  3. DefenseClaw /api/v1/inspect/response  (completion guardrail, observe)   (Qwen3-8B, CPU)
     │  4. emit llm.request ──────────────────►  REAL Splunk HEC :8088, index=axis
     ▼                                                            sourcetype axis:llm
   response streamed back to the client unchanged
```

## Two planes, one index

| Plane | Producer | Event | sourcetype |
|-------|----------|-------|------------|
| tool  | `axis_mcp_connector` | `axis.toolcall` | `axis:toolcall` |
| inference | `lemonade_proxy` | `llm.request` | `axis:llm` |

Both carry the same `identity{session,user,tenant,device_id}` block, so a single
agent session's tool calls and LLM calls correlate in `index=axis` by
`identity.session`.

## Why a proxy (not a Lemonade patch)

Lemonade is upstream AMD code; patching it to emit Splunk events would rot against
every release. A transparent proxy keeps the telemetry entirely on the client
side, reuses the connector's exact `SplunkEventSink`/HEC pattern, and works for
**any** Anthropic-speaking host (Claude Code, gaia, curl) unchanged. The proxy
never alters the bytes it forwards — parsing (model/prompt/token usage) is
best-effort telemetry, never on the data path.

## DefenseClaw on the inference plane

DefenseClaw already ships the endpoints:

- `POST /api/v1/inspect/request` — scans the **prompt** (prompt-injection / jailbreak).
- `POST /api/v1/inspect/response` — scans the **completion** (secret / PII leakage).

The proxy runs both in **observe** mode and **fail-open** by default: a
governance-sidecar hiccup must never take inference down, and a false positive on
a prompt must never kill a chat turn (DefenseClaw itself demotes prompt-surface
blocks to "alert"). Each `llm.request` event records `would_block`, so Cisco can
tune the ruleset before flipping to action mode.

**Privacy by default:** the event ships metadata only — model, timing, token
counts, prompt/response **char counts**, and the DefenseClaw verdicts. It does
**not** ship prompt or completion text (mirrors the connector shipping
exit/duration, not stdout). DefenseClaw sees the content to scan it; Splunk sees
only the verdict.

## What it proves

1. **proxy is transparent** — `/v1/messages` (JSON and SSE) is forwarded
   byte-for-byte; the client sees an unmodified Lemonade response.
2. **deterministic HARD proof** — a real `/v1/messages` call through the proxy
   produces an `llm.request(decision=allow)` event **read back out of
   `index=axis`** via the Splunk search API, carrying the DefenseClaw prompt
   verdict. Model-independent.
3. **Claude Code through the proxy** (best-effort) — Claude Code's own inference,
   pointed at the proxy, lands its `llm.request` events in Splunk under session
   `cc-lemon`. Reported SKIP if the local 8B can't carry Claude Code's loop (the
   deterministic stage still HARD-proves the plane).

## Reuse (no duplication)

- `../../stack/lemonade_proxy/` — the proxy + 22 unit tests (new).
- `../../stack/lemonade/run_lemonade.sh` — local Lemonade on CPU.
- `../../stack/defenseclaw/run_gateway.sh` — the real DefenseClaw gateway.
- `../../stack/splunk/install_splunk.sh` + `query_splunk.sh` — real Splunk + read-back.

## Layout

```
lemonade_test/
  README.md  SETUP.md  RESULTS.md
  run_lemonade_telemetry.sh   end-to-end runner (the main new code)
  claude_job.sh               Claude Code with ANTHROPIC_BASE_URL -> proxy
  artifacts/                  SUMMARY.txt, events.jsonl, splunk_query.txt, proxy_*.log
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd lemonade_test
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_lemonade_telemetry.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
