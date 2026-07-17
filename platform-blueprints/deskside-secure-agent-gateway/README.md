<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AMD Deskside Agent Gateway

A self-contained, **fully open-source** secure gateway for coding agents that
runs entirely on **one machine** — no orchestrator, no rack control plane, no
third-party SaaS. It governs an agent (e.g. Claude Code) on **two planes** so
that every action it takes is sandboxed and audited:

- **Tool / audit plane** — the agent's built-in tools are disabled; the *only*
  way it can touch the machine is a single MCP `run` tool. Every call flows
  through an **AXIS** sandbox (Landlock + seccomp + netns) → a **SQLite audit
  event**. Nothing runs unrecorded.
- **Inference plane** — completions flow through a transparent **Lemonade
  proxy** that optionally consults a **semantic router** to keep cheap prompts
  on a local model and escalate hard ones to a frontier model, and emits an
  `llm.request` audit event correlated to the tool plane by a shared session id.

All audit events land in a local **SQLite database** — no Splunk, no external
service, no network dependency. The DB is queryable with any SQL tool or the
bundled Python helper.

Validated on **AMD Strix Halo** (Ryzen AI Max+ 395), unprivileged.

> **AXIS *contains* every call at execution time. SQLite records *what
> happened*.** The deep-dive architecture reference is in
> [`stack/README.md`](./stack/README.md).

## What's here

| Path | What it is |
|------|------------|
| [`stack/`](./stack/) | The gateway itself — the MCP connector, the inference proxy, Lemonade + SQLite wiring, and the Strix Halo bring-up. Start here. |
| [`tests/agent_harness_integrations/`](./tests/agent_harness_integrations/) | End-to-end demos of the gateway driving real agents (Claude Code, gaia) on real tasks. |
| [`tests/router_test/`](./tests/router_test/), [`tests/lemonade_test/`](./tests/lemonade_test/) | Inference-plane A/B and telemetry verification suites. |
| [`experiments/`](./experiments/) | Benchmarks: isolation latency and router tokenomics. |

## Prerequisites

The gateway builds its external binaries for you (see [`stack/SETUP.md`](./stack/SETUP.md)).
You need on the box first:

- **Node ≥18** (via nvm) — the connector + proxy.
- **git, curl, python3** — clone/build.
- An **AXIS** sandbox binary — built from source by `stack/platforms/halo/setup.sh` (Rust).
- A local **Lemonade** server *or* a frontier LLM key (e.g. an Anthropic-compatible
  gateway) for the inference plane.
- **SQLite** — ships with Python and is used automatically; no install needed.

One-time bring-up on a Strix Halo deskside:

```bash
cd stack
source platforms/halo/env.sh     # toolchain paths, native AXIS policy, ports
bash   platforms/halo/setup.sh   # build Go, Rust, AXIS; run unit tests
bash   platforms/halo/run.sh     # functional governance loop
```

## Quick start A — Claude Code solves a SWE-bench issue, fully governed

Drives **Claude Code** to solve the real SWE-bench instance `pallets__flask-5014`
end-to-end. Claude Code's own tools are disabled, so every command it runs is
sandboxed by AXIS and audited in the local SQLite DB.

```bash
cd tests/agent_harness_integrations/claude_code

# inference via an Anthropic-compatible gateway
GATEWAY_KEY=<your-key> bash run_swebench_client.sh

# or inference via the Claude API directly
INFERENCE_MODE=anthropic ANTHROPIC_API_KEY=<key> bash run_swebench_client.sh
```

Green means: Claude Code emitted `mcp__axis__run`, the edit was persisted to
the repo under the sandbox, the `axis.toolcall` events are in the SQLite audit
DB, and the graded FAIL_TO_PASS test passes (`SOLVED=yes`). See
[`claude_code/README.md`](./tests/agent_harness_integrations/claude_code/README.md).

## Quick start B — a gaia agent through the same connector

Proves the **same** connector governs a *different* MCP host: AMD's
[gaia](https://github.com/amd/gaia) agent framework. gaia drives the `run` tool
through AXIS → SQLite, unchanged — one connector, two hosts.

```bash
cd tests/agent_harness_integrations/gaia
GATEWAY_KEY=<your-key> bash run_gaia_integration.sh
```

## Results

All measured on a **Strix Halo** deskside (AMD Ryzen AI Max+ PRO 395), unprivileged.

### Governance loop — works end-to-end

| Suite | Result | Date |
|-------|--------|------|
| Connector + proxy unit tests | **42 + 83 pass / 0 fail** | 2026-07-15 |
| Functional loop (`run_integration.sh`) — ALLOW sandboxed, a dangerous command contained by AXIS (denied syscall → `decision=deny`), both planes correlate under one session | **green** | 2026-07-15 |

### Isolation cost — near-container security at near-native latency

Per-tool-call sandbox cost, p50, N=30 ([`experiments/latency_bench/`](./experiments/latency_bench/RESULTS.md)):

| Mechanism | p50 latency | vs bare subprocess |
|-----------|------------:|-------------------:|
| subprocess (no isolation — floor) | 2.1 ms | 1× |
| **AXIS** (Landlock + seccomp + netns) | **19.8 ms** | **~9×** |
| Docker | 244.7 ms | ~116× |
| Firecracker (micro-VM) | 460.6 ms | ~219× |
| gVisor (runsc) | 493.4 ms | ~235× |

AXIS wraps *every* tool call in a fresh sandbox for tens of milliseconds — real
Landlock+seccomp isolation ~12× cheaper than Docker and ~23× cheaper than a
micro-VM.

### Tokenomics — a local model offloads real cost

τ-bench (50 tasks) × semantic router, frontier = Opus 4.8, local =
Qwen3-Coder-30B on the APU ([`experiments/tokenomics_tau_bench/`](./experiments/tokenomics_tau_bench/RESULTS.md)):

| Metric | Router on | Frontier-only |
|--------|----------:|--------------:|
| Turns served locally | **15.7%** | 0% |
| Total cost (50 tasks) | **$28.26** | $31.19 |
| Net saving | **9.4% ($2.92)** | — |
| Tasks solved | 36 / 50 | 38 / 50 |

## License

Released under the MIT License — see [`LICENSE`](./LICENSE).

### Third-party components

This blueprint integrates the following open-source components, each governed by its own license:

| Component | Role | License |
|-----------|------|---------|
| [AXIS](https://github.com/qedawkins/axis) | Per-tool-call sandbox (Landlock + seccomp + netns) | Apache-2.0 |
| [Lemonade SDK](https://github.com/lemonade-sdk/lemonade) | Local LLM inference server (CPU/APU, GGUF models) | Apache-2.0 |
| [vLLM Semantic Router](https://github.com/vllm-project/semantic-router) | Per-prompt difficulty-based routing (consult-only) | Apache-2.0 |
| [gaia](https://github.com/amd/gaia) | AMD agent framework (second MCP host in the gaia demo) | MIT |
| [better-sqlite3](https://github.com/WiseLibs/better-sqlite3) | Synchronous SQLite bindings for Node.js — audit event sink | MIT |

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
