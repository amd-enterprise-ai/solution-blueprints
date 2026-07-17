<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Tokenomics_tau_bench — Router cost/quality A/B

An A/B benchmark measuring whether the gateway's semantic router
([`../../stack/`](../../stack/)) reduces frontier-model cost without lowering task
quality. [τ-bench](https://github.com/sierra-research/tau-bench) (retail + airline
customer-service tasks) is run over the gateway under two configurations:

- **Arm A (router-on):** the semantic router classifies each turn and serves it
  from the local model (`Qwen3-Coder-30B`) or the frontier model (`Opus 4.8`).
- **Arm B (frontier-only):** every turn is served by the frontier model.

Both arms run the same 50 seed=42 tasks (25 retail + 25 airline), on a CPU-only
node (repeated for stability) and independently on a Strix Halo iGPU deskside.
See [`RESULTS.md`](./RESULTS.md) for the measured cost and quality, findings, and
reproduction steps.

## Files

- `run_tokenomics_ab.sh` — the A/B harness (starts the router and proxy, runs both arms).
- `analyze.py` — aggregates the event logs into cost, quality, and call counts.
- `select_tasks.py` — deterministic task selection (seed=42), regenerates `data/`.
- `router/config.yaml` — router difficulty config; the `threshold` is the
  cost/quality dial.
- [`RESULTS.md`](./RESULTS.md) — the verified runs, findings, and reproducibility.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
