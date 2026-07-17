<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Tokenomics A/B — τ-bench × vLLM Semantic Router

**Run dates:** 2026-07-14 (CPU-only node, 3 replicates) · 2026-07-09 (Strix Halo)

**Platform:** CPU-only node (e.g., volcano node; AMD EPYC, no GPU), **3 replicates** — primary result below. Independently validated on a Strix Halo iGPU deskside.

---

## Setup

| Component | Detail |
|-----------|--------|
| **Benchmark** | τ-bench v0.1 (sierra-research/tau-bench), retail + airline environments |
| **Tasks** | 50 tasks: 25 retail + 25 airline, seed=42 (deterministic, same for both arms) |
| **Frontier model** | `claude-opus-4-8` via AMD LLM Gateway, $5.00/1M in · $25.00/1M out |
| **Local model** | `Qwen3-Coder-30B-A3B-Instruct-GGUF` (Q4_K_M, 18.6 GB, MoE ~3B active), ctx=200K, on the llama.cpp CPU backend (CPU node) / Lemonade iGPU (Halo) |
| **Semantic router** | vLLM semantic-router, difficulty-based classify API, consult-only |
| **Proxy** | `stack/lemonade_proxy` — routes calls, captures telemetry |

---

## Arms

| Arm | Description |
|-----|-------------|
| **A (router-on)** | τ-bench agent → `lemonade_proxy` (`LEMON_ROUTER=on`) → per-turn classify → local Qwen3-30B OR frontier Opus 4.8 |
| **B (frontier-only)** | τ-bench agent → `lemonade_proxy` (`LEMON_FORCE_FRONTIER=1`) → every call → Opus 4.8 |

Both arms use `--temperature 1` (required for Opus 4.8), `--agent-strategy tool-calling`, `--user-strategy llm` (simulated user also uses Opus 4.8 through the proxy).

---

## Results

The full A/B was run **three times** on the CPU-only node; all numbers are **mean ± sd** across the three replicates, so they reflect run-to-run stability rather than a single sample.

| Metric (mean ± sd, 3 runs) | Arm A (router-on) | Arm B (frontier-only) | A vs B |
|---|---|---|---|
| Calls → local (Qwen3-30B) | **16.3% ± 0.6** (162 of 988 calls) | 0% | **+16% kept off the frontier** |
| Calls → frontier (Opus 4.8) | 83.7% | 100% | −16% |
| **Total cost** | **$27.86 ± 1.31** | $31.48 ± 1.06 | **−$3.62 (−11.5%)** ↓ |
| **Task quality** (avg reward) | **0.680 ± 0.020** | 0.687 ± 0.050 | **−0.007** → same quality |

*Task quality = average τ-bench reward: each task scores **1 if solved correctly, 0 if not**, so 0.68 means 68% of tasks solved. Higher is better.*

### Same quality, checked task-by-task

Comparing the arms on the same task (150 comparisons: 50 tasks × 3 runs):

| Task-by-task comparison | Result |
|---|---|
| Tasks solved — router-on / frontier-only | 102 / 150 · 103 / 150 |
| Router-on failures also failed by frontier-only | 38 / 48 (79%) |
| Disagreements — router-on worse / better | 10 / 9 |
| Avg per-task quality difference (95% CI) | −0.007 ([−0.06, +0.05], includes 0) |

### Cost vs quality: tuning the routing threshold

Lowering the threshold sends more turns to the local model. Sweeping it (Arm A, one run per point) traces the trade-off:

| Threshold | Handled locally | Total cost (Arm A) | Task quality (avg reward) | Saving vs frontier-only¹ |
|---|---|---|---|---|
| **0.10** (default) | **16%** | $27.86 | **0.68** | ~11% |
| 0.05 | 45% | $21.09 | 0.60 | ~33% |
| 0.02 | 63% | $14.29 | 0.50 | ~55% |
| 0.00 | 82% | $5.58 | 0.34 | ~82% |

¹ vs Arm B frontier-only (~$31.5, reward ≈ 0.69). The 0.10 row is the 3-replicate mean; the other rows are single Arm-A runs.

---

## Key Findings

### 1. The router achieves real local offload (16%) and saves ~11% cost

Serving ~16% of turns from the local model lowered total spend from $31.48 to $27.86 (−11.5%), stable across three replicates. On the CPU node the local tier carries no metered energy cost.

### 2. Small quality trade-off (−0.007 reward)

Router-on solved 102/150 tasks vs frontier-only's 103/150 — a −0.007 average reward gap, well within run-to-run noise (95% CI [−0.06, +0.05] includes 0). In other words, turning routing on delivers the same task quality as sending everything to the frontier.

### 3. The cost/quality balance is operator-tunable

The local share is governed by a single classification threshold, not fixed by the choice of models. The default (0.10) sits at the knee of the curve — meaningful local share at parity quality — and lowering it moves along a smooth trade-off curve, up to ~82% of turns served locally at the all-local floor, so each deployment can select its own operating point. Because the threshold is defined on semantic difficulty, it behaves consistently when models are swapped: only the achievable (cost, quality) points shift, not the mechanism.

### 4. A smarter classifier could send even more work to the local model

The router decides local vs frontier by how much a message *sounds like* a hard reasoning problem. Many customer-service requests — like "book a flight from NYC to LA" — are actually simple, structured tasks, but they don't "sound" simple to the classifier, so they get sent to the frontier anyway. A classifier built for customer-service (judging things like how many steps or tool calls a request needs) could safely route more of these to the local model — more savings, same quality.

---

## Independent validation on Strix Halo (iGPU)

The identical A/B — same harness, proxy, router config, models, and the same 50 seed=42 tasks — was also run on a **Strix Halo deskside (AMD Ryzen AI Max+ PRO 395)**, a single run with full GPU instrumentation. No source code differs between platforms. The headline economics match the CPU node:

| Metric | Strix Halo (iGPU, 1 run) | CPU-only node (mean ± sd, 3 runs) |
|---|---|---|
| Calls handled locally | 15.7% | 16.3% ± 0.6 |
| Net cost saving A vs B | 9.4% | 11.5% ± 1.8% |
| Task quality (avg reward) A / B | 0.720 / 0.760 | 0.680 / 0.687 |
| Wall-clock duration A / B | 58 / 49 min | 55.8 / 48.7 min |

### Call distribution (Halo)

| Metric | Arm A (router-on) | Arm B (frontier-only) |
|--------|-------------------|-----------------------|
| Total LLM calls | 959 | 1,058 |
| Calls → local (Qwen3-30B) | **151 (15.7%)** | 0 (0%) |
| Calls → frontier (Opus 4.8) | 808 (84.3%) | 1,058 (100%) |
| Router classify decisions | 151 `local-simple` · 808 `frontier-reasoning` | — |

### Cost (Halo)

| Cost component | Arm A | Arm B |
|----------------|-------|-------|
| Frontier cost (Opus 4.8) | $28.2634 | $31.1869 |
| Local energy (GPU, 19.4 kJ) | $0.0009 | $0.0000 |
| **Total cost** | **$28.2643** | **$31.1869** |
| **Net saving A vs B** | **$2.92 (9.4%)** | — |

### Local energy cost is negligible — the deskside economics work

The Halo run has a GPU energy meter, so it can price the local tier directly. At US electricity rates ($0.17/kWh):

- Local: **~$0.0000059 / call** (0.0006 cents)
- Frontier: **~$0.035 / call** (3.5 cents)
- **Local is ~5,900× cheaper per call**

---

## Reproducibility

```bash
cd tokenomics_tau_bench

# Prerequisites
# On the Strix Halo deskside, first `source ../../stack/platforms/halo/env.sh`
# to put lemonade-server on PATH and set that box's toolchain, TMPDIR, and ports.
export LEMONADE_CTX_SIZE=200000
lemonade-server serve --port 13305 &  # Lemonade with 200K ctx

export GATEWAY_KEY="<AMD-Gateway-Ocp-Apim-Key>"
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export REQUESTS_CA_BUNDLE=$SSL_CERT_FILE CURL_CA_BUNDLE=$SSL_CERT_FILE
export NODE_EXTRA_CA_CERTS=$SSL_CERT_FILE

# Run (both arms)
bash run_tokenomics_ab.sh > run.log 2>&1

# Results
cat artifacts/SUMMARY.txt
```

Task selection is deterministic (seed=42, 25 retail + 25 airline). Re-running `select_tasks.py` produces the same indices.

**On a CPU-only node (e.g., volcano):** same command; start Lemonade with the llama.cpp CPU backend (`--llamacpp cpu`). Only two settings are CPU-specific: `ROUTER_CPUS` pins the router to its own cores so its embedding classify is not starved by local inference, and `ROUTER_CLASSIFY_TIMEOUT_MS` is raised because classify is slower on CPU.

The 3 replicates and the threshold sweep need no code changes — just re-run the same command:

- **3 replicates:** run it three times (saving each run to its own output folder), then average the results.
- **Threshold sweep:** change one number — the routing threshold in `router/config.yaml` — to 0.05, 0.02, then 0.00, and re-run the router-on arm once for each.

---

## Next Steps

1. **Add domain-specific difficulty signals** (constraint count, tool count, multi-step planning) to the classifier so more turns can offload locally *at the same quality* — i.e. shift the whole trade-off curve up, not just move along it.
2. **Run with a stronger local model** — Devstral-Small-2507 (coding + tool-calling, 14GB) may raise reward at every offload level since it's more focused on agentic tool use than the general-purpose Qwen3-Coder.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
