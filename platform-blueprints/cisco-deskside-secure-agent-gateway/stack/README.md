<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Architecture deep-dive: Claude Code + Lemonade + AXIS + DefenseClaw + Splunk

![Deskside secure agent gateway architecture](./assets/architecture.png)

The **deskside secure agent gateway** governs a coding agent entirely on **one
machine** — no orchestrator, no rack control plane. The optional **LLM router**
runs locally as a *consult-only* step inside the inference proxy (see below).

> This is the architecture reference. For the project overview and copy-paste
> quick-starts, start at the [top-level README](../README.md).

**Validated on Strix Halo** — the deskside target (AMD Ryzen AI Max+ 395,
unprivileged). Reproduce from [`platforms/halo/`](./platforms/halo/); setup in
[`SETUP.md`](./SETUP.md); results in [`RESULTS.md`](./RESULTS.md); adversarial
red-team in [`REDTEAM_FINDINGS.md`](./REDTEAM_FINDINGS.md).

A coding agent (**Claude Code**) is governed on **both planes**:

- **Tool / audit plane** — every side-effecting action goes through a **new MCP
  connector** that (1) wraps each tool call in an **AXIS** sandbox and runs it
  locally, (2) submits the call to a **Cisco DefenseClaw** gateway for admission /
  guardrail enforcement, and (3) builds **Splunk-HEC-shaped audit events** +
  manages **agent session identity**, writing them to a local sink.
- **Inference plane** — completions flow through a transparent **Lemonade
  telemetry proxy** ([`lemonade_proxy/`](./lemonade_proxy/)) that forwards each
  request byte-for-byte to the local Lemonade server while, on the side, running
  a DefenseClaw prompt/completion guardrail, optionally **consulting the vLLM
  Semantic Router** for a per-prompt tier decision (`LEMON_ROUTER=on`), and
  emitting an `llm.request` audit event (with a `routing` block) to the same
  Splunk `index=axis`.

## The two-plane model


![Client-Side Integration: two-plane governance model](./assets/architecture.png)

- **Inference plane** — Claude Code points `ANTHROPIC_BASE_URL` at the
  **lemonade_proxy**, not directly at Lemonade. The proxy forwards each request
  byte-for-byte to Lemonade's Anthropic-compatible API (a quantized Qwen3 model
  served locally on the APU), and on the side runs a
  DefenseClaw prompt/completion guardrail and emits an `llm.request` event. With
  `LEMON_ROUTER=on` it also **consults** the vLLM Semantic Router per prompt: a
  hard prompt gets a **frontier** decision (escalate to a paid Anthropic-compatible
  gateway, e.g. AMD LLM Gateway `claude-*`) and a simple prompt stays **local**.
  The router is consult-only and **fail-open** — a router hiccup, or a frontier
  decision with no key configured, keeps the request on the local tier. Full A/B
  in [`../tests/router_test/`](../tests/router_test/).
- **Tool / audit plane** — Claude Code is launched with `Bash`, `Read`,
  `Write`, `Edit`, … **disallowed**, so the *only* way the model can act on the
  machine is the connector's `run` tool. That gives **complete audit coverage**:
  every action flows through DefenseClaw + AXIS + the Splunk event builder.

**DefenseClaw = policy/verdict layer. AXIS = isolation/enforcement layer. The
Splunk events = the audit record.** They are complementary: DefenseClaw decides
*whether* a call may run; AXIS *contains* it when it does; the event records
*what happened*.

## What is Cisco DefenseClaw?

[DefenseClaw](https://github.com/cisco-ai-defense/defenseclaw) (open source,
Apache-2.0) is a **governance shell for agentic AI**. It provides:

- **Admission control** — scan skills / MCP servers / plugins before they're
  trusted.
- **Runtime guardrails** — inspect live `tool_call` / `tool_result` traffic with
  regex rule packs, policy, CodeGuard, and an optional LLM judge. Its compiled-in
  rules already flag credential-file reads (`~/.ssh/id_*`, `~/.aws/credentials`,
  `~/.git-credentials`), reverse shells, `curl … | bash`, `rm -rf /…`, writes to
  `/etc`, and inline secret material (AWS/GitHub/Anthropic/Stripe/… keys).
- **observe vs action modes** — in **action** mode a HIGH/CRITICAL finding
  **blocks** the call; in **observe** mode it's downgraded to allow and only
  logged (the verdict still carries `would_block`).
- **A Go gateway sidecar** (`defenseclaw-gateway`) exposing a **REST API on
  :18970** and streaming telemetry to Splunk.

**How this connector uses it:** the connector is a DefenseClaw *enforcement
client*. Before AXIS runs a tool call, the connector POSTs the `tool_call` to
the gateway's `POST /api/v1/inspect/tool`; the gateway returns a verdict
(`action`, `severity`, `findings`, `would_block`). In action mode a HIGH/CRITICAL
block means **AXIS never runs the command**. After execution the `tool_result`
can optionally be posted back for output scanning. If the gateway is
unreachable, behavior is governed by `DEFENSECLAW_FAIL_OPEN` (default
**fail-closed** = block).

## Layout

```
stack/
  README.md                 this file
  SETUP.md                  step-by-step bring-up on a Strix Halo deskside
  RESULTS.md                verified run results
  package.json              root npm package (for mcp_probe.mjs)
  axis_mcp_connector/       the NEW MCP connector (Node, @modelcontextprotocol/sdk)
    src/
      server.js             MCP stdio server; registers `run` + `session_info`
      identity.js           agent session identity (session/user/tenant/device, seq)
      axis.js               AXIS argv build + sandboxed exec + log stripping
      defenseclaw.js        DefenseClaw gateway REST client
      splunk_events.js      Splunk-HEC event builder + local JSONL sink
      trace.js              per-turn trace reader (reads the proxy's trace statefile)
      otel.js               OTEL envelope (event_id, schema_version, resource, ...)
    test/                   node --test unit tests
  lemonade_proxy/           the INFERENCE-plane telemetry proxy (Node)
    src/
      server.js             transparent reverse proxy; guardrail + router + llm.request
      router.js             SemanticRouterClient (consult-only classify, fail-open)
      defenseclaw.js        DefenseClaw inference client (observe/fail-open)
      identity.js           per-session identity for llm.* events
      anthropic.js          request/response + SSE parsing (Anthropic + OpenAI shapes)
      llm_events.js         llm.request/session builder (+ routing/gpu/otel blocks) + sink
      trace.js              per-turn trace authority (mints trace on a new user turn, writes statefile)
      otel.js               OTEL envelope + GenAI (gen_ai.*) span attributes
      gpu.js                amdgpu-sysfs GPU sampling for local inference (busy/mem/power/energy)
    test/                   node --test unit tests (routing, cross-plane, OTEL, trace, GPU)
  defenseclaw/
    run_gateway.sh          build + run defenseclaw-gateway on :18970
    defenseclaw.policy.yaml gateway config (guardrail.mode=action, api_port)
  lemonade/
    run_lemonade.sh         install Lemonade, serve a local GGUF model on the APU
  splunk/                   vendored user-space Splunk install + search-API query
  fake_hec.py               local HEC sink for offline/dev runs (self-contained)
  mcp.json                  example .mcp.json registering the `axis` connector
  mcp_probe.mjs             scripted MCP client (control-plane test, model-independent)
  run_integration.sh        functional runner: does the governed loop work end-to-end?
  run_redteam.sh            adversarial runner: can a determined agent break out?
  make_cisco_session.sh     capture ONE full agent session (both planes) -> a Cisco deliverable dir
  scripts/group_by_trace.py render a capture as a per-turn trace view (by_trace.md)
  platforms/                per-machine bring-up profiles (NOT stack components)
    halo/                   Strix Halo deskside: env/setup/run + native AXIS policy
  artifacts/                test outputs
```

### Two test suites (functional vs adversarial)

The loop is verified from two complementary angles — kept in separate runners
because their pass/fail meaning is opposite:

- **`run_integration.sh` — functional (positive).** Green = the governed loop
  works: an allowed command runs sandboxed, the *expected* block is blocked
  (stage 4), and both planes audit under one session. Results:
  [`RESULTS.md`](./RESULTS.md).
- **`run_redteam.sh` — adversarial (negative).** Green = attacks are *contained*:
  DefenseClaw regex evasion, sandbox escape, audit fail-open, resource
  exhaustion. It runs `discovery` (find holes) and `regression` (fail on any
  breach) modes and writes [`REDTEAM_FINDINGS.md`](./REDTEAM_FINDINGS.md). Where
  stage 4 proves the block path *works*, the red-team asks whether it can be
  *bypassed*.

## The connector pipeline (per `run` call)

1. **identity** — ensure the session is started (emit `axis.session_start`
   once); assign a `seq`. Session id from `AXIS_SESSION` or a minted `cc-<uuid>`;
   carries `user` / `tenant` / `device_id`.
2. **DefenseClaw admit** — POST `{tool, args:{argv,cwd}, direction:"tool_call",
   session_id}` to the gateway. In action mode a HIGH/CRITICAL block ⇒ skip
   execution, return a blocked result.
3. **AXIS exec** (only if allowed) — `axis run --policy <p> -- bash -c "<cmd>"`,
   capturing stdout/stderr/exit, with AXIS's own banners stripped.
4. **DefenseClaw inspect result** (optional, `DEFENSECLAW_INSPECT_RESULT=1`).
5. **Splunk event** — build an `axis.toolcall` event (identity + policy +
   redacted command + `decision` + result exit/duration + DefenseClaw findings),
   append to the JSONL sink and optionally POST to a local HEC.
6. return stdout/stderr/exit to Claude Code.

On shutdown (stdin close / SIGTERM): emit `axis.session_end`.

The event schema is stable across both planes
(`axis.session_start | toolcall | session_end`, `identity.session`,
`policy.source`, `command.argv_redacted`, `decision`, `result.exit`) so they
land the same shape in Splunk.

## The inference-proxy pipeline (per completion, `lemonade_proxy/`)

The proxy is a transparent reverse proxy: non-message paths (health, model list)
are forwarded silently; only `POST /v1/messages` and `/v1/chat/completions`
produce telemetry. Per audited request:

1. **identity** — emit `llm.session_start` once; assign a `seq`.
2. **DefenseClaw request guardrail** — POST the prompt to
   `/api/v1/inspect/request` (**observe + fail-open** on the inference plane, so
   a gateway hiccup never takes inference down; in action mode a block
   short-circuits upstream with a 403).
3. **routing decision** (only if `LEMON_ROUTER=on`) — `router.route(prompt)`
   POSTs to the semantic-router classify API (`/api/v1/classify/intent`, **no
   inference, no Envoy**) and maps the recommended model to a **tier**: a
   `claude-*` / frontier-model recommendation ⇒ `frontier`, else `local`. Any
   error/timeout ⇒ `local` (fail-open).
4. **forward** — to the local Lemonade upstream **byte-for-byte**; only on a
   *honored* frontier escalation (router says frontier **and** a frontier key is
   set) does the proxy swap the upstream base, attach the frontier auth header,
   and rewrite the body `model`. A frontier decision without a key is **recorded
   but served local** (fail-safe).
5. **additive response headers** — `x-lemon-router`, `x-lemon-tier`,
   `x-lemon-selected-model`, `x-lemon-complexity` (the body is never altered).
6. **DefenseClaw response guardrail** — POST the completion to
   `/api/v1/inspect/response` (observe).
7. **Splunk event** — build an `llm.request` event (identity + model + endpoint +
   timing + token counts + verdicts + a **`routing` block**) into the same
   `index=axis` (`sourcetype=axis:llm`); `routing` is `null` on a plain
   passthrough build (router disabled). See
   [`TELEMETRY_CONTRACT.md`](./TELEMETRY_CONTRACT.md) §8.

On shutdown: emit `llm.session_end`. The two tiers:

| Tier | Backend | Cost | Route |
|------|---------|------|-------|
| local | Lemonade `Qwen3-8B-GGUF` on CPU (`:13305`) | free | simple / factual prompts |
| frontier | AMD LLM Gateway `claude-*` (Anthropic-compatible; configurable) | paid | hard reasoning / proofs / planning |

## One session id across both planes

The two planes run as **separate processes** with **independent lifecycles**
(each mints its own `*.session_start`/`*.session_end`, and `seq` counts per
plane). They only line up in Splunk if they stamp the **same**
`identity.session` — so a single search returns an agent's LLM calls *and* its
tool calls for one logical run. Getting that shared id is a small env-var
contract.

**How each plane resolves `identity.session`:**

| Plane | Source of truth | Resolution order | Minted fallback |
|-------|-----------------|------------------|-----------------|
| Tool / audit (`axis_mcp_connector`) | `AXIS_SESSION` | `AXIS_SESSION` | `cc-<uuid>` |
| Inference (`lemonade_proxy`) | `AXIS_SESSION` (with an `LLM_SESSION` override) | `LLM_SESSION` → `AXIS_SESSION` | `lp-<uuid>` |

**The contract: export one `AXIS_SESSION` and leave `LLM_SESSION` unset.**
Whatever launches Claude Code sets `AXIS_SESSION`; both planes inherit it (the
connector uses it directly, the proxy falls back to it because `LLM_SESSION` is
unset), so both emit under the same id:

```bash
# launcher sets ONE session id; both planes inherit it (LLM_SESSION stays unset)
export AXIS_SESSION="cc-$(uuidgen)"      # e.g. cc-9f31…
#   tool plane   -> identity.session = $AXIS_SESSION   (connector)
#   inference    -> identity.session = $AXIS_SESSION   (proxy, LLM_SESSION unset)
```

The result in the sink / `index=axis` — six events, two planes, **one id**:

```
llm.session_start    cc-9f31…      (sourcetype=axis:llm)
llm.request          cc-9f31…      (sourcetype=axis:llm)
axis.session_start   cc-9f31…      (sourcetype=axis:toolcall)
axis.toolcall        cc-9f31…      (sourcetype=axis:toolcall)
axis.session_end     cc-9f31…
llm.session_end      cc-9f31…
```

```spl
# both planes for one logical agent run
index=axis identity.session="cc-9f31…" | sort time
```

**Footgun:** setting a per-plane `LLM_SESSION` (or a different `AXIS_SESSION` per
process) makes the proxy stamp a *different* id and **breaks** correlation —
`LLM_SESSION` exists only as a deliberate per-plane override. With nothing
injected at all, each plane mints its own prefixed id (`cc-…` vs `lp-…`) so
unrelated runs never collide by accident.

This is proven end-to-end by `run_integration.sh` **stage 5** (boots the proxy
under the connector's `AXIS_SESSION` and asserts both planes emit one
`identity.session`) and locked at the code level by
`lemonade_proxy/test/cross_plane_session.test.js` (a future env-var rename or
fallback-order change fails the unit test). See
[`TELEMETRY_CONTRACT.md`](./TELEMETRY_CONTRACT.md) "the correlation seam".

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `AXIS_BIN` | `axis` | AXIS binary |
| `AXIS_POLICY` | `/etc/axis/coding-agent.yaml` | AXIS policy file |
| `DEFENSECLAW_URL` | `http://127.0.0.1:18970` | gateway REST base |
| `DEFENSECLAW_GATEWAY_TOKEN` | _(none)_ | Bearer token for the gateway REST API (required: DefenseClaw ≥0.8 fails closed on every route but `GET /health`) |
| `DEFENSECLAW_MODE` | `action` | `action` blocks HIGH/CRITICAL; `observe` logs only |
| `DEFENSECLAW_FAIL_OPEN` | `0` | `1` = allow when gateway unreachable |
| `DEFENSECLAW_INSPECT_RESULT` | `0` | `1` = also POST tool_result |
| `SPLUNK_SINK` | _(none)_ | JSONL audit sink path |
| `SPLUNK_HEC_URL` | _(none)_ | optional local HEC to POST events to |
| `SPLUNK_HEC_TOKEN` | `fake-token` | HEC token |
| `AXIS_SESSION` | minted `cc-<uuid>` | session id |
| `AXIS_TRACE_STATE` | `${TMPDIR}/axis-trace-<session>.json` | shared per-turn trace statefile (proxy writes, connector reads); export the same value to both planes |
| `AXIS_USER` / `AXIS_TENANT` / `AXIS_DEVICE_ID` | derived | identity fields. `AXIS_USER` unset ⇒ the resolved OS login user (`identity.user_source=os`); set ⇒ `user_source=env`. No auth yet, so `user` is asserted — `user_source` records the trust level. Passed into DefenseClaw for per-user policy. |

### Inference proxy (`lemonade_proxy/`)

| Var | Default | Meaning |
|-----|---------|---------|
| `LEMON_PROXY_PORT` | `13399` | proxy listen port |
| `LEMON_UPSTREAM` | `http://127.0.0.1:13305` | local Lemonade upstream |
| `DEFENSECLAW_INFERENCE_MODE` | `observe` | inference-plane guardrail mode |
| `DEFENSECLAW_INFERENCE_FAIL_OPEN` | `1` | `0` = block when gateway unreachable |
| `DEFENSECLAW_INSPECT_RESPONSE` | `1` | `0` = skip completion guardrail |
| `LEMON_ROUTER` | `off` | `on` = consult the semantic router per prompt |
| `SEMANTIC_ROUTER_URL` | `http://127.0.0.1:8088` | classify API base (pick a port that doesn't collide with the Splunk HEC, e.g. `:18088`) |
| `FRONTIER_UPSTREAM` | `https://<llm-gateway>/Anthropic` | frontier tier base (Anthropic-compatible) |
| `FRONTIER_MODEL` | `claude-opus-4.8` | model id written into the body on escalation |
| `FRONTIER_AUTH_HEADER` | `Ocp-Apim-Subscription-Key` | frontier auth header name (`x-api-key` for Anthropic direct) |
| `FRONTIER_AUTH_KEY` | `$GATEWAY_KEY` | frontier key; **absent ⇒ frontier decisions serve local (fail-safe)** |
| `FRONTIER_EXTRA_HEADERS` | `{}` | JSON of extra headers (e.g. `{"anthropic-version":"2023-06-01"}`) |
| `GPU_TELEMETRY` | `on` | `off` disables the local-inference GPU sampling block on `llm.request` |
| `GPU_SYSFS_PATH` | _(auto-discovered)_ | pin the amdgpu card device dir (`/sys/class/drm/cardN/device`) instead of auto-detecting |
| `LLM_CAPTURE_CONTENT` | `off` | `on` = also land the raw user prompt + LLM answer text in an `llm.request.content` block. **Ships potentially sensitive text to `index=axis`** — off by default |
| `LLM_CAPTURE_MAX_CHARS` | `8192` | per-side truncation cap for captured prompt/completion text |
| `LLM_USER` | `$AXIS_USER` | inference-plane user override; same `env`/`os` resolution + `user_source` as the tool plane |
| `AXIS_TRACE_STATE` | `${TMPDIR}/axis-trace-<session>.json` | shared per-turn trace statefile (this plane is the trace authority; it writes, the connector reads) |
| `SPLUNK_SINK` / `SPLUNK_HEC_URL` / `SPLUNK_HEC_TOKEN` | _(shared)_ | same audit sink as the tool plane |

## Quick start

See [SETUP.md](./SETUP.md). The fastest validation is the **control-plane
probe** (model-independent):

```bash
cd stack
npm install && (cd axis_mcp_connector && npm install)
(cd axis_mcp_connector && node --test)     # connector unit tests (tool plane)
(cd lemonade_proxy && node --test)         # proxy unit tests (routing + cross-plane + OTEL + trace + GPU)
bash run_integration.sh                    # full end-to-end on one machine
```

The **inference proxy + semantic router A/B** (baseline vs `LEMON_ROUTER=on`,
with the routing block verified in real Splunk) has its own end-to-end runner in
[`../tests/router_test/`](../tests/router_test/).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
