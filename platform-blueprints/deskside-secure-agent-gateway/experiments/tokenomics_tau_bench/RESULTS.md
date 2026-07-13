<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Tokenomics A/B — τ-bench × vLLM Semantic Router on Strix Halo

**Run date:** 2026-07-09
**Host:** a Strix Halo deskside (AMD Ryzen AI Max+ PRO 395)
**Duration:** ~1h 47m total (Arm A: 58 min, Arm B: 49 min)

---

## Setup

| Component | Detail |
|-----------|--------|
| **Benchmark** | τ-bench v0.1 (sierra-research/tau-bench), retail + airline environments |
| **Tasks** | 50 tasks: 25 retail + 25 airline, seed=42 (deterministic, same for both arms) |
| **Frontier model** | `claude-opus-4-8` via AMD LLM Gateway, $5.00/1M in · $25.00/1M out |
| **Local model** | `Qwen3-Coder-30B-A3B-Instruct-GGUF` (Q4_K_M, 18.6 GB, MoE ~3B active) on Lemonade v9.1.4, ctx=200K |
| **Semantic router** | vLLM semantic-router, difficulty-based classify API, consult-only |
| **Proxy** | `stack/lemonade_proxy` — routes calls, captures telemetry |
| **US electricity** | $0.17/kWh (EIA ~2026 average) |

---

## Arms

| Arm | Description |
|-----|-------------|
| **A (router-on)** | τ-bench agent → `lemonade_proxy` (`LEMON_ROUTER=on`) → per-turn classify → local Qwen3-30B OR frontier Opus 4.8 |
| **B (frontier-only)** | τ-bench agent → `lemonade_proxy` (`LEMON_FORCE_FRONTIER=1`) → every call → Opus 4.8 |

Both arms use `--temperature 1` (required for Opus 4.8), `--agent-strategy tool-calling`, `--user-strategy llm` (simulated user also uses Opus 4.8 through the proxy).

---

## Results

### Call distribution

| Metric | Arm A (router-on) | Arm B (frontier-only) |
|--------|-------------------|-----------------------|
| Total LLM calls | 959 | 1,058 |
| Calls → local (Qwen3-30B) | **151 (15.7%)** | 0 (0%) |
| Calls → frontier (Opus 4.8) | 808 (84.3%) | 1,058 (100%) |
| Router classify decisions | 151 `local-simple` · 808 `frontier-reasoning` | — |

### Token usage

| | Arm A | Arm B |
|---|---|---|
| Frontier input tokens | 5,091,261 | 5,611,811 |
| Frontier output tokens | 112,285 | 125,115 |
| Local input tokens (est) | 284,620 | 0 |
| Local output tokens (est) | 7,882 | 0 |

### Cost

| Cost component | Arm A | Arm B |
|----------------|-------|-------|
| Frontier cost (Opus 4.8) | $28.2634 | $31.1869 |
| Local energy (GPU, 19.4 kJ) | $0.0009 | $0.0000 |
| **Total cost** | **$28.2643** | **$31.1869** |
| **Net saving A vs B** | **$2.92 (9.4%)** | — |

### Task quality (reward)

τ-bench reward is binary per-task: 1 = correct outcome, 0 = incorrect. Measured by comparing the agent's actions against the ground-truth action sequence.

| | Arm A | Arm B | Delta |
|---|---|---|---|
| Tasks solved (reward=1) | 36 / 50 | 38 / 50 | −2 |
| **Average reward** | **0.720** | **0.760** | **−0.040** |
| Retail avg reward | 0.840 | 0.880 | −0.040 |
| Airline avg reward | 0.600 | 0.640 | −0.040 |

---

## Key Findings

### 1. The router achieves real local offload (16%) and saves 9.4% cost

τ-bench's shorter, more conversational turns gave the router meaningful signals. **15.7% of agent turns were classified `local-simple`** — primarily short acknowledgements, simple confirmations, and single-fact lookups — and were served by the local Qwen3-Coder-30B model.

This produced a **9.4% cost saving ($2.92 on 50 tasks)**. Extrapolated to a production customer-service deployment handling thousands of sessions per day, this represents a meaningful budget reduction.

### 2. Local energy cost is negligible — the deskside economics work

The 151 local calls consumed **19.4 kJ** total (38.8W average × ~140s inference time). At US electricity rates:

- Local cost per call: **~$0.0000059** (0.006 cents)
- Frontier cost per call: **~$0.035** (3.5 cents)
- **Local is ~5,900× cheaper in energy terms than frontier**

When the router correctly offloads a call locally, the economics are compelling. The constraint is which prompts qualify.

### 3. Small quality trade-off (−0.04 reward)

Arm A solved 36/50 tasks vs Arm B's 38/50 — a −0.04 average reward gap. The local model handled "simple" turns adequately but occasionally provided less precise or shorter responses that caused task failure. Airline tasks were harder (0.600 vs 0.640) — multi-step rebooking constraints may require more accurate follow-through than the local model provides.

**This is a tunable dial:** stricter routing thresholds (sending fewer turns to local) would close the quality gap at the cost of less local offload.

### 4. Router's difficulty classifier misses some τ-bench complexity

The router classifies based on linguistic similarity to hard ("prove this step by step", "design an algorithm") vs easy ("what is the capital") candidates. Customer-service turns don't map cleanly onto these — "book a flight from NYC to LA" scores as `medium→frontier-reasoning` even though it's a structured API call. This explains why 84% still went frontier despite τ-bench's mix of simple/complex tasks.

A better classifier for customer-service would use domain-specific signals (number of constraints, number of required tool calls) rather than academic reasoning difficulty.

---

---

## Reproducibility

```bash
cd tokenomics_tau_bench

# Prerequisites
export LEMONADE_CTX_SIZE=200000
lemonade-server serve --port 13305 &  # Lemonade with 200K ctx

export GATEWAY_KEY="<AMD-Gateway-Ocp-Apim-Key>"
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export REQUESTS_CA_BUNDLE=$SSL_CERT_FILE CURL_CA_BUNDLE=$SSL_CERT_FILE
export NODE_EXTRA_CA_CERTS=$SSL_CERT_FILE
source ../../stack/platforms/halo/env.sh

# Run (both arms, ~1h 45m total)
bash run_tokenomics_ab.sh > run.log 2>&1

# Results
cat artifacts/SUMMARY.txt
```

Task selection is deterministic (seed=42, 25 retail + 25 airline). Re-running `select_tasks.py` produces the same indices.

---

## Next Steps

1. **Tune the router threshold** for customer-service workloads — add domain-specific difficulty signals (constraint count, tool count, multi-step planning) to push local offload toward 30–40% without quality loss.
2. **Measure quality vs offload tradeoff** systematically: vary the routing threshold from strict (only obvious simple turns) to lenient (any medium-complexity turn) and plot reward vs cost saving.
3. **Run with a stronger local model** — Devstral-Small-2507 (coding + tool-calling, 14GB) may close the reward gap since it's more focused on agentic tool use than the general-purpose Qwen3-Coder.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
