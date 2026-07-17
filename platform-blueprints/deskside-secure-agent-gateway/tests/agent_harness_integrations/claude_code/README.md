<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side SWE-bench Test: Claude Code + AMD LLM Gateway + AXIS + **SQLite audit DB**

Solves one real **SWE-bench** instance (`pallets__flask-5014`) through the **client-side**
governance loop and proves every tool call is audited end-to-end in a local **SQLite audit DB**.

It uses the same control/audit plane as the rest of the blueprint (`axis_mcp_connector`, the AXIS
sandbox as the sole enforcement layer, a local SQLite audit DB) and points it at a real coding task.
This is the single-machine version: there is **no orchestrator and no rack control plane** — the
connector runs each command locally under AXIS and writes the audit event straight to SQLite.

```
            Claude Code (claude-opus-4.8 via AMD LLM Gateway)   (not sandboxed)
                 │ inference: ANTHROPIC_BASE_URL + Ocp-Apim-Subscription-Key
                 │ tools: .mcp.json -> ONLY mcp__axis__run
                 ▼
        axis MCP connector (Node, reused from gateway)
                 │ identity -> AXIS sandbox (sole enforcement) -> SQLite audit event
                 ▼
   AXIS sandbox (Landlock+seccomp+netns)              SQLite audit DB
   read_write on the flask workspace                  AUDIT_DB (default artifacts/audit.db)
   (edits persist to host)                            events read back with SQL
```

## What it proves (HARD checks)

1. The AMD LLM Gateway answers a real `claude-opus-4.8` completion from the machine.
2. **Functional solve** — real Claude Code, driven by the frontier model, emits `mcp__axis__run`,
   edits `src/flask/blueprints.py` (the edit **persists to the host repo** via the AXIS `read_write`
   rule), and the resulting `axis.toolcall(decision=allow)` + `axis.session_start` events are
   **written to the SQLite audit DB and read back out of it with SQL**.
3. **Grade (soft, reported)** — the official `test_patch` is applied and the FAIL_TO_PASS test
   (`test_empty_name_not_allowed`) is run → `SOLVED=yes/no` recorded in `SUMMARY.txt` (does not gate
   the integration result).

A silent write failure cannot pass: the audit assertions read the event back out of the SQLite DB,
not from an in-memory sink.

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
- `../../lib/audit_db.sh` — shared SQLite audit-DB read-back helpers
- `./task/instance.json` + `grade.sh` — the task definition + deterministic grader (vendored)

## Layout

```
claude_code/
  README.md  SETUP.md  RESULTS.md
  run_swebench_client.sh   end-to-end runner (the main new code)
  claude_job.sh            launches Claude Code against the gateway (run-tool-only, cwd=workspace)
  prompt.txt               the task prompt (uses mcp__axis__run)
  mcp.json.tmpl            .mcp.json template (connector env incl. AUDIT_DB + swebench policy)
  artifacts/               outputs (SUMMARY.txt, audit.db, claude_cc.out, …)
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd tests/agent_harness_integrations/claude_code

# default: AMD LLM Gateway
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
  bash run_swebench_client.sh

# alt: Claude API direct
INFERENCE_MODE=anthropic ANTHROPIC_API_KEY=<key> \
  bash run_swebench_client.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
