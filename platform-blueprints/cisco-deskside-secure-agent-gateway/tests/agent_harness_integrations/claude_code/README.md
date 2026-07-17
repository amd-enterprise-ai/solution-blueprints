<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side SWE-bench Test: Claude Code + AMD LLM Gateway + AXIS + DefenseClaw + **real Splunk**

Solves one real **SWE-bench** instance (`pallets__flask-5014`) through the **client-side**
governance loop and proves every tool call is audited end-to-end in a **real Splunk**.

It uses the same control/audit plane as the rest of the blueprint (`axis_mcp_connector`, DefenseClaw
gateway, AXIS sandbox, real Splunk HEC + search verification) and points it at a real coding task.
This is the single-machine version: there is **no orchestrator and no rack control plane** — the
connector runs each command locally under AXIS and ships the audit event straight to Splunk.

```
            Claude Code (claude-opus-4.8 via AMD LLM Gateway)   (not sandboxed)
                 │ inference: ANTHROPIC_BASE_URL + Ocp-Apim-Subscription-Key
                 │ tools: .mcp.json -> ONLY mcp__axis__run
                 ▼
        axis MCP connector (Node, reused from gateway)
                 │ identity -> DefenseClaw admission -> AXIS sandbox -> Splunk event
                 ▼
   DefenseClaw :18970 (action)   AXIS sandbox (seccomp+landlock+netns)   REAL Splunk
                                  read_write on the flask workspace        HEC :8088, index=axis
                                  (edits persist to host)                  search API :8089
```

## What it proves (HARD checks)

1. The AMD LLM Gateway answers a real `claude-opus-4.8` completion from the machine.
2. **Functional solve** — real Claude Code, driven by the frontier model, emits `mcp__axis__run`,
   edits `src/flask/blueprints.py` (the edit **persists to the host repo** via the AXIS `read_write`
   rule), and the resulting `axis.toolcall(decision=allow)` + `axis.session_start` events are
   **POSTed to the real Splunk HEC and read back out of `index=axis` via the search API**.
3. **Grade (soft, reported)** — the official `test_patch` is applied and the FAIL_TO_PASS test
   (`test_empty_name_not_allowed`) is run → `SOLVED=yes/no` recorded in `SUMMARY.txt` (does not gate
   the integration result).

A silent HEC failure cannot pass: the Splunk assertions read the event back from the index, not from
the local sink.

## Inference modes & platforms

The tool/audit plane is identical everywhere; only where the model runs changes:

- **`INFERENCE_MODE=gateway`** (default) — Claude Code → AMD LLM Gateway
  (`claude-opus-4.8`, `Ocp-Apim-Subscription-Key`).
- **`INFERENCE_MODE=anthropic`** — Claude Code → `api.anthropic.com` directly
  (`claude-opus-4-8`, `ANTHROPIC_API_KEY`/`x-api-key`).

**Validated on:**

- **Strix Halo deskside** (Ryzen AI Max+ 395, unprivileged) — default gateway path with the AXIS
  `axis_native` backend (Landlock+seccomp) and zeroed process limits, since the box has no
  lxc/netns helper or writable cgroups-v2; results in [`RESULTS.md`](./RESULTS.md).
  Override `AXIS_RUNTIME_PROVIDER` / `AXIS_*_LIMIT_*` on a machine with those privileges available.

## Reuse (no duplication)

- `../../../stack/axis_mcp_connector/` — connector + the connector unit tests (unchanged)
- `../../../stack/defenseclaw/run_gateway.sh` — the real DefenseClaw gateway
- `../../../stack/splunk/install_splunk.sh` + `query_splunk.sh` — real Splunk install + search read-back
- `./task/instance.json` + `grade.sh` — the task definition + deterministic grader (vendored)

## Layout

```
claude_code/
  README.md  SETUP.md  RESULTS.md
  run_swebench_client.sh   end-to-end runner (the main new code)
  claude_job.sh            launches Claude Code against the gateway (run-tool-only, cwd=workspace)
  prompt.txt               the task prompt (uses mcp__axis__run)
  mcp.json.tmpl            .mcp.json template (connector env incl. real Splunk HEC + swebench policy)
  artifacts/               outputs (SUMMARY.txt, events.jsonl, splunk_query.txt, claude_cc.out, …)
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd tests/agent_harness_integrations/claude_code

# default: AMD LLM Gateway
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_swebench_client.sh

# alt: Claude API direct
INFERENCE_MODE=anthropic ANTHROPIC_API_KEY=<key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_swebench_client.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
