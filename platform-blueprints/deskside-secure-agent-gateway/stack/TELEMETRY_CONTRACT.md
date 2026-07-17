<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AMD Deskside Agent Gateway — Telemetry Contract

**Status:** stable
**Producers:**
- **Tool plane** — `axis_mcp_connector` (Node stdio MCP server) emits `axis.*` events.
- **Inference plane** — `lemonade_proxy` (Node reverse proxy) emits `llm.*` events.

**Transport:** SQLite database (`AUDIT_DB`, default `./audit.db`). Both planes write
to the same file using `better-sqlite3` (synchronous, no network required).

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  time    REAL,
  event   TEXT,
  session TEXT,
  data    TEXT   -- full event JSON
);
```

**Querying:**

```python
import sqlite3, json
db = sqlite3.connect("audit.db")
for (data,) in db.execute("SELECT data FROM events ORDER BY id"):
    print(json.loads(data))
```

**Two planes, one DB.** Both producers write to `AUDIT_DB` and share the same
`identity{session, user, user_source, tenant, device_id}` block, so an agent
session's tool calls (`axis.toolcall`) and its LLM calls (`llm.request`) correlate
by `identity.session`.

**Session id seam:** inject one `AXIS_SESSION` and leave `LLM_SESSION` unset —
both planes carry the same id. Locked by `lemonade_proxy/test/cross_plane_session.test.js`.

---

## 1. Context

```
agent → run(command) → AXIS sandbox (sole enforcement) → SQLite audit event
```

Lifecycle per session:

```
axis.session_start   (once, on first tool call)
axis.toolcall        (one per run() call, seq = 0,1,2,…)
axis.session_end     (once, on shutdown)
```

---

## 2. Common fields (every event)

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `event` | string | `axis.toolcall` | event type |
| `time` | number (epoch s) | `1782887146.175` | event creation time |
| `identity.session` | string | `cc-3f2a…` | session id |
| `identity.user` | string | `<your-user>` | acting user |
| `identity.user_source` | string enum | `<your-user-source>` | `env` \| `os` \| `sso` \| `unknown` |
| `identity.tenant` | string | `<your-tenant>` | tenant / org unit |
| `identity.device_id` | string | `<device-hostname>` | host/device |

**`identity.user` resolution:** no auth yet — value is asserted.
`user_source` records the trust level (`env` = launcher-set, `os` = OS login user,
`sso` = reserved for future auth). Shared logic: `stack/shared/identity_utils.js`.

`session_start` and `toolcall` additionally carry:

| Field | Type | Description |
|-------|------|-------------|
| `policy.id` | string | AXIS policy identifier in force |
| `policy.source` | string | where the policy came from |

---

## 3. Event types — tool plane

### 3.1 `axis.session_start`

```json
{
  "event": "axis.session_start",
  "time": 1782887161.785,
  "identity": {
    "session": "cc-3f2a…",
    "user": "<your-user>",
    "user_source": "<your-user-source>",
    "tenant": "<your-tenant>",
    "device_id": "<device-hostname>"
  },
  "policy": { "id": "coding-agent", "source": "local-control" }
}
```

### 3.2 `axis.toolcall`

**Example A — allowed:**

```json
{
  "event": "axis.toolcall",
  "time": 1782887161.858,
  "identity": { "session": "cc-3f2a…", "user": "<your-user>", "user_source": "<your-user-source>", "tenant": "<your-tenant>", "device_id": "<device-hostname>" },
  "policy": { "id": "coding-agent", "source": "local-control" },
  "command": {
    "seq": 0,
    "argv_redacted": ["bash", "-c", "echo AGENT_OK && hostname"]
  },
  "decision": "allow",
  "result": { "exit": 0, "duration_ms": 45, "timed_out": false }
}
```

**Example B — contained (AXIS Landlock denied the read, command exited non-zero):**

```json
{
  "event": "axis.toolcall",
  "time": 1782887200.512,
  "identity": { "session": "cc-3f2a…", "user": "<your-user>", "user_source": "<your-user-source>", "tenant": "<your-tenant>", "device_id": "<device-hostname>" },
  "policy": { "id": "coding-agent", "source": "local-control" },
  "command": {
    "seq": 4,
    "argv_redacted": ["bash", "-c", "cat ~/.ssh/id_rsa"]
  },
  "decision": "error",
  "result": { "exit": 1, "duration_ms": 12, "timed_out": false }
}
```

### 3.3 `axis.session_end`

```json
{
  "event": "axis.session_end",
  "time": 1782887169.681,
  "identity": { "session": "cc-3f2a…", "user": "<your-user>", "user_source": "<your-user-source>", "tenant": "<your-tenant>", "device_id": "<device-hostname>" }
}
```

---

## 4. Field reference — `axis.toolcall`

### `command`
| Field | Type | Description |
|-------|------|-------------|
| `seq` | integer | 0-based, monotonic per session |
| `argv_redacted` | string[] | the executed argv with recognised secrets masked as `<redacted>` |

Only the **redacted** argv is persisted — the raw command is never written to the
audit DB. AXIS performs no command-string inspection, so `redactCommand()`
(masking known key shapes: `AKIA…`, `ghp_…`, `sk-ant-…`, `sk-…`, `xox[b-s]-…`,
and `--password/--token/--secret/--api-key` / `*_TOKEN=`/`*_SECRET=`/`*_KEY=`
values) is the only guard preventing an inline secret from landing in the store.

### `decision`

AXIS (Landlock + seccomp + netns) is the sole tool-plane enforcement layer;
`decision` is the connector's disposition after the sandbox runs.

| Value | Meaning |
|-------|---------|
| `allow` | AXIS ran the command to a clean exit (exit == 0) |
| `error` | AXIS ran the command but it exited non-zero — an ordinary command failure **or** a Landlock/seccomp/netns denial (the exit code alone cannot distinguish them, so this is **not** labelled `deny`) |
| `block` | execution refused before AXIS ran (reserved; e.g. audit sink unavailable; exit == null) |
| `unknown` | no exit observed |

### `result`
| Field | Type | Description |
|-------|------|-------------|
| `exit` | integer \| null | process exit code; `null` when not run |
| `duration_ms` | integer \| null | wall-clock execution time |
| `timed_out` | boolean | true if AXIS killed the command |

---

## 5. SQL queries — tool plane

```sql
-- every audited tool call in a session
SELECT data FROM events WHERE session='cc-3f2a…' AND event='axis.toolcall' ORDER BY id;

-- commands that exited non-zero (ordinary failure OR an AXIS sandbox denial)
SELECT data FROM events WHERE event='axis.toolcall'
  AND json_extract(data, '$.decision') = 'error';

-- reconstruct action order
SELECT json_extract(data, '$.command.seq'),
       json_extract(data, '$.command.argv_redacted')
FROM events WHERE session='cc-3f2a…' AND event='axis.toolcall' ORDER BY id;
```

---

## 6. Inference plane — `llm.*` events (`lemonade_proxy`)

```
host → proxy → [local Lemonade | frontier gateway] → SQLite llm.request
```

**Privacy:** metadata only (model, timing, token counts, char counts). The raw
prompt and completion text are **never** stored — only their character counts.

### 6.1 `llm.request`

```json
{
  "event": "llm.request",
  "time": 1782887300.421,
  "identity": { "session": "cc-lemon", "user": "<your-user>", "user_source": "<your-user-source>", "tenant": "<your-tenant>", "device_id": "<device-hostname>" },
  "policy": { "id": "inference-proxy", "source": "local-control" },
  "request": { "seq": 0, "model": "Qwen3-8B-GGUF", "endpoint": "/v1/messages", "stream": true, "messages": 2, "prompt_chars": 148 },
  "decision": "allow",
  "routing": null,
  "gpu": null,
  "result": { "status": 200, "duration_ms": 8421, "prompt_tokens": 41, "completion_tokens": 12, "completion_chars": 63, "stop_reason": "end_turn" }
}
```

### 6.2 Field reference — `llm.request`

| Field | Type | Description |
|-------|------|-------------|
| `request.seq` | integer | 0-based per session |
| `request.model` | string | model id served |
| `request.endpoint` | string | `/v1/messages` or `/v1/chat/completions` |
| `request.stream` | boolean | SSE response |
| `request.messages` | integer | message count |
| `request.prompt_chars` | integer | flattened prompt length (not the text) |
| `decision` | string | `allow` \| `unknown` |
| `result.status` | integer | upstream HTTP status |
| `result.duration_ms` | integer | wall-clock time |
| `result.prompt_tokens` | integer \| null | input tokens |
| `result.completion_tokens` | integer \| null | output tokens |
| `result.completion_chars` | integer \| null | completion char count |
| `result.stop_reason` | string \| null | model stop reason |
| `routing` | object \| null | semantic router decision (null when router disabled) |
| `gpu` | object \| null | APU consumption block (local tier only) |

### 6.3 SQL queries — inference plane

```sql
-- every LLM call in a session
SELECT data FROM events WHERE session='cc-lemon' AND event='llm.request' ORDER BY id;

-- token spend per model
SELECT json_extract(data, '$.request.model'),
       SUM(CAST(json_extract(data, '$.result.completion_tokens') AS INTEGER))
FROM events WHERE event='llm.request' GROUP BY 1;

-- correlate both planes for a session
SELECT json_extract(data, '$.time'), json_extract(data, '$.event')
FROM events WHERE session='cc-lemon' ORDER BY id;

-- tier mix
SELECT json_extract(data, '$.routing.tier'), COUNT(*)
FROM events WHERE event='llm.request' AND json_extract(data, '$.routing') IS NOT NULL GROUP BY 1;
```

### 6.4 Routing response headers (`x-lemon-*`)

| Header | Value |
|--------|-------|
| `x-lemon-router` | `on` \| `off` |
| `x-lemon-tier` | `local` \| `frontier` |
| `x-lemon-selected-model` | model name |
| `x-lemon-complexity` | e.g. `needs_reasoning:hard` |

---

## 7. Privacy — no raw text stored

The inference plane records **metadata only**: model, timing, token counts, and
prompt/completion **character counts**. The raw user prompt and the LLM answer
are never written to the audit DB. (There is deliberately no opt-in to store
them.) The tool plane likewise persists only the **redacted** argv, never the
raw command — see §4.

---

## 8. OTEL envelope + per-turn traces

Every event carries an OTEL-shaped envelope (additive — SQLite is the source of truth).

| Field | Description |
|-------|-------------|
| `event_id` | uuid, globally unique |
| `schema_version` | `"1.0"` |
| `ingest_source` | `axis-mcp` \| `lemonade-proxy` |
| `trace_id` | 32-hex per-turn trace id |
| `span_id` | 16-hex this event's span |
| `parent_span_id` | turn's root span |
| `resource` | OTEL Resource (service.name, service.namespace, …) |

**Trace model:** one user prompt + all LLM/tool calls it triggers = one `trace_id`.
The inference proxy is the trace authority; it writes to `AXIS_TRACE_STATE`, which
the tool connector reads.

```sql
-- reconstruct one turn (both planes)
SELECT json_extract(data, '$.time'), json_extract(data, '$.event')
FROM events WHERE json_extract(data, '$.trace_id') = '4bf92f…' ORDER BY id;
```

---

## 9. GPU consumption (`llm.request.gpu`)

For local-tier inference (Lemonade on the AMD APU), sampled from amdgpu sysfs.
`null` on frontier tier and when no AMD GPU present.

| Field | Unit |
|-------|------|
| `busy_percent` / `busy_percent_avg` | % |
| `vram_used_bytes` / `vram_total_bytes` | bytes |
| `power_w` / `power_avg_w` | W |
| `energy_joules` | J |
| `temp_c` | °C |
| `sclk_mhz` | MHz |

---

*Source: `stack/axis_mcp_connector/src/sqlite_events.js` (tool plane),
`stack/lemonade_proxy/src/sqlite_events.js` (inference plane),
`stack/shared/identity_utils.js` (identity).*

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
