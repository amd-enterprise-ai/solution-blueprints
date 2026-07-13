<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Client-Side gaia Test: the axis MCP connector driven by **gaia** (a 2nd MCP host) + **real Splunk**

Proves the **same** client-side `axis_mcp_connector` that Claude Code uses also works when the MCP
host is [**gaia**](https://github.com/amd/gaia) (AMD's agent framework) — every gaia-driven tool
call flows through DefenseClaw → AXIS → a **real Splunk**, and the index ends up holding events from
**both** a gaia session and a Claude-Code session, demonstrating one connector serving two hosts.

This is the gaia sibling of [`../claude_code/amd_gateway_test/`](../claude_code/amd_gateway_test/). The
entire control/audit plane is unchanged (same connector, DefenseClaw gateway, AXIS sandbox, real
Splunk HEC + search verification). Only the **MCP host** changes: gaia instead of — and in addition
to — Claude Code. No connector code is modified; it is reused unchanged by path.

```
   gaia (MCP host)                         Claude Code (MCP host)
     │ MCPClient.from_config / Agent          │ .mcp.json -> mcp__axis__run
     │ (gaia.mcp.client.MCPClient)            │
     └──────────────┬─────────────────────────┘
                    ▼
        axis MCP connector (Node, reused from gateway)
                    │ identity -> DefenseClaw admission -> AXIS sandbox -> Splunk event
                    ▼
   DefenseClaw :18970 (action)   AXIS sandbox (seccomp+landlock+netns)   REAL Splunk
                                                                          HEC :8088, index=axis
                                                                          search API :8089
```

## What it proves

1. **gaia speaks to the connector** — gaia's own MCP client (`gaia.mcp.client.MCPClient`,
   registered from an `mcp_servers.json` carrying the full connector env) connects and lists the
   `run` tool.
2. **gaia deterministic probe (HARD)** — gaia's MCP client invokes `run('echo GAIA_OK && hostname')`
   under session `gaia-probe`; real sandbox output comes back, and the
   `axis.toolcall(decision=allow)` event is **read back out of `index=axis` via the Splunk search
   API**. This is model-independent — no LLM is involved, so it cannot be blocked by gaia↔gateway
   inference wiring.
3. **cross-host** — a Claude-Code run-tool call (session `cc-gaia`) lands its own event in the same
   index, and the final check confirms `index=axis` holds **both** a gaia session and a Claude-Code
   session.
4. **gaia agentic** — a gaia `Agent` whose LLM is **`Qwen3-8B-GGUF` on CPU via the local Lemonade
   server** decides on its own to call the `run` tool (session `gaia-agent`); the event is confirmed
   in Splunk. gaia uses its native Lemonade provider (its built-in Claude/OpenAI providers don't
   honour a custom gateway base_url). If Lemonade is unavailable the stage is reported **SKIP** (the
   stage-2 deterministic probe still HARD-proves the gaia↔connector↔Splunk integration).

A silent HEC failure cannot pass: the Splunk assertions read the event back from the index, not from
the local sink.

## Reuse (no duplication)

- `../../../stack/axis_mcp_connector/` — connector + the connector unit tests (unchanged)
- `../../../stack/defenseclaw/run_gateway.sh` — the real DefenseClaw gateway
- `../../../stack/splunk/install_splunk.sh` + `query_splunk.sh` — real Splunk install + search read-back
- `../claude_code/amd_gateway_test/claude_job.sh` — the cross-host Claude-Code launcher (gateway)

## Layout

```
gaia/
  README.md  SETUP.md  RESULTS.md
  run_gaia_integration.sh   end-to-end runner (the main new code)
  gaia_mcp_probe.py         deterministic HARD proof: gaia's MCPClient drives the connector's run
  gaia_agent_query.py       best-effort agentic: a gaia Agent calls the tool via the gateway
  artifacts/                outputs (SUMMARY.txt, events.jsonl, splunk_query.txt, gaia_*.out, …)
```

## Quick start

See [SETUP.md](./SETUP.md).

```bash
cd tests/agent_harness_integrations/gaia
GATEWAY_KEY=<Ocp-Apim-Subscription-Key> \
SPLUNK_PASS=<SPLUNK_PASS> HEC_TOKEN=<HEC_TOKEN> \
  bash run_gaia_integration.sh
```

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
