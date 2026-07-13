#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# make_cisco_session.sh — capture ONE full agent session through the client-side
# governance loop and package it as a self-contained deliverable for Cisco.
#
# It brings up the whole local stack — fake HEC + real DefenseClaw gateway +
# Lemonade + the inference proxy — under ONE AXIS_SESSION and ONE shared
# AXIS_TRACE_STATE, then drives a small MULTI-TURN agent workload so the capture
# shows Cisco's telemetry deltas end to end:
#   * per-turn trace_ids  (one user prompt + its LLM calls + its tool calls = 1 trace)
#   * OTEL-shaped events   (trace_id/span_id/parent_span_id, gen_ai.*, resource, ...)
#   * GPU consumption      (gpu block on local-tier llm.request)
#
# Two drivers:
#   RUN_CC=1 (default if `claude` present) — real Claude Code, multi-turn, via the proxy
#   probe fallback           — mcp_probe.mjs tool calls + direct proxy /v1/messages,
#                              scripted so the deliverable is deterministic even when
#                              the local 8B won't reliably emit tool calls.
#
# Output: artifacts/cisco_session_<ts>/ with events.ndjson, by_trace.md,
# claude_transcript.txt, README.md, SCHEMA.md  (+ a .tgz next to it).
#
# Env: AXIS_BIN, AXIS_POLICY, DC_PORT, HEC_PORT, LEMONADE_PORT, PROXY_PORT,
#      LEMON_MODEL, RUN_CC. Source platforms/halo/env.sh first on Strix Halo.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONN="$HERE/axis_mcp_connector"
SERVER="$CONN/src/server.js"
PROBE="$HERE/mcp_probe.mjs"
PROXY="$HERE/lemonade_proxy/src/server.js"

AXIS_BIN="${AXIS_BIN:-axis}"
AXIS_POLICY="${AXIS_POLICY:-/etc/axis/coding-agent.yaml}"
DC_PORT="${DC_PORT:-18970}"
HEC_PORT="${HEC_PORT:-18088}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
PROXY_PORT="${PROXY_PORT:-13399}"
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
HEC_TOKEN="client-fake-token"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$HERE/artifacts/cisco_session_$TS"
mkdir -p "$OUT"
HEC_CAP="$OUT/events.ndjson"          # every HEC event lands here (both planes)
SINK="$OUT/sink.jsonl"                # local JSONL sink (same events)
SESS="cc-cisco-$TS"
TRACE_STATE="$(mktemp "${TMPDIR:-/tmp}/axis-trace-cisco.XXXXXX.json")"

log(){ echo "[cisco-session] $*"; }
PIDS=()
cleanup(){
  for p in "${PIDS[@]:-}"; do kill "$p" >/dev/null 2>&1 || true; done
  [ -n "${DEFENSECLAW_HOME:-}" ] && [ -f "$DEFENSECLAW_HOME/gateway.pid" ] && kill "$(cat "$DEFENSECLAW_HOME/gateway.pid")" 2>/dev/null || true
}
trap cleanup EXIT

# node from nvm.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
NODE_BIN_DIR="$(dirname "$(ls -t "$NVM_DIR"/versions/node/*/bin/node 2>/dev/null | head -1)" 2>/dev/null)"
export PATH="$HOME/.local/bin:${NODE_BIN_DIR:-}:$PATH"
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }

# RUN_CC=1 drives with the real `claude` binary (needs an Anthropic-compatible
# upstream). The client-side Lemonade here is OpenAI-only, so on this box the
# deterministic scripted probe (OpenAI chat/completions through the same proxy +
# mcp_probe tool calls) is the default. Set RUN_CC=1 explicitly when pointing at
# an Anthropic-compatible upstream (e.g. AMD LLM Gateway / a C++ Lemonade build).
RUN_CC="${RUN_CC:-0}"

# --- 1. fake HEC ----------------------------------------------------------
log "starting fake HEC on :$HEC_PORT -> $HEC_CAP"
python3 "$HERE/fake_hec.py" --port "$HEC_PORT" --out "$HEC_CAP" --token "$HEC_TOKEN" >"$OUT/hec.log" 2>&1 &
PIDS+=("$!")
for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$HEC_PORT/health" >/dev/null 2>&1 && break; sleep 0.1; done

# --- 2. DefenseClaw gateway ----------------------------------------------
export DC_PORT
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-cs-cisco-$$}"
bash "$HERE/defenseclaw/run_gateway.sh" >"$OUT/gateway_boot.txt" 2>&1 &
PIDS+=("$!")
DC_UP=0
for _ in $(seq 1 150); do curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1 && { DC_UP=1; break; }; sleep 0.4; done
[ "$DC_UP" -eq 1 ] && export DEFENSECLAW_HOME="$(grep -oE 'DEFENSECLAW_HOME=.*' "$OUT/gateway_boot.txt" | tail -1 | cut -d= -f2-)"
log "DefenseClaw up=$DC_UP"

# --- shared connector/proxy env (ONE session, ONE trace statefile) --------
export AXIS_BIN AXIS_POLICY
export AXIS_SESSION="$SESS"
export AXIS_TRACE_STATE="$TRACE_STATE"
export DEFENSECLAW_URL="http://127.0.0.1:$DC_PORT"
export DEFENSECLAW_MODE="action"
export DEFENSECLAW_FAIL_OPEN="0"
export SPLUNK_SINK="$SINK"
export SPLUNK_HEC_URL="http://127.0.0.1:$HEC_PORT"
export SPLUNK_HEC_TOKEN="$HEC_TOKEN"
export AXIS_TENANT="client-deskside"
export AXIS_USER="${USER:-amd}"

# --- 3. Lemonade ----------------------------------------------------------
log "starting Lemonade ($LEMON_MODEL) on :$LEMONADE_PORT"
LEMON_UP=0
if LEMONADE_PORT="$LEMONADE_PORT" LEMON_MODEL="$LEMON_MODEL" bash "$HERE/lemonade/run_lemonade.sh" >"$OUT/lemonade_boot.txt" 2>&1; then
  curl -sf "http://127.0.0.1:$LEMONADE_PORT/api/v1/health" >/dev/null 2>&1 && LEMON_UP=1
fi
log "Lemonade up=$LEMON_UP"
[ "$LEMON_UP" -eq 1 ] || { log "FATAL: Lemonade required for the session capture"; exit 2; }

# --- 4. inference proxy (in front of Lemonade, same session + trace state) -
log "starting inference proxy on :$PROXY_PORT"
LEMON_PROXY_PORT="$PROXY_PORT" \
LEMON_UPSTREAM="http://127.0.0.1:$LEMONADE_PORT" \
  node "$PROXY" >"$OUT/proxy_boot.txt" 2>&1 &
PIDS+=("$!")
PROXY_UP=0
for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$PROXY_PORT/api/v1/health" >/dev/null 2>&1 && { PROXY_UP=1; break; }; sleep 0.2; done
log "proxy up=$PROXY_UP"
[ "$PROXY_UP" -eq 1 ] || { log "FATAL: proxy failed to start"; exit 2; }

# --- 5. drive a MULTI-TURN agent workload --------------------------------
if [ "$RUN_CC" -eq 1 ]; then
  log "=== driver: real Claude Code (multi-turn) via the proxy ==="
  cat > "$OUT/.mcp.json" <<EOF
{ "mcpServers": { "axis": { "command": "node", "args": ["$SERVER"],
  "env": { "AXIS_BIN": "$AXIS_BIN", "AXIS_POLICY": "$AXIS_POLICY",
    "AXIS_SESSION": "$SESS", "AXIS_TRACE_STATE": "$TRACE_STATE",
    "DEFENSECLAW_URL": "http://127.0.0.1:$DC_PORT", "DEFENSECLAW_MODE": "action",
    "DEFENSECLAW_GATEWAY_TOKEN": "$DEFENSECLAW_GATEWAY_TOKEN",
    "AXIS_TENANT": "client-deskside", "AXIS_USER": "$AXIS_USER",
    "SPLUNK_SINK": "$SINK", "SPLUNK_HEC_URL": "http://127.0.0.1:$HEC_PORT",
    "SPLUNK_HEC_TOKEN": "$HEC_TOKEN" } } } }
EOF
  # Two user turns in one CLI session so >=2 trace_ids appear.
  PROMPT='Do these as two separate steps, using the run tool for each shell command. Step 1: run "uname -a && echo STEP1_OK". After you get the result, Step 2: run "echo STEP2_OK && hostname". Then stop.'
  ANTHROPIC_BASE_URL="http://127.0.0.1:$PROXY_PORT" \
  ANTHROPIC_AUTH_TOKEN="lemonade-local" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="$LEMON_MODEL" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="$LEMON_MODEL" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$LEMON_MODEL" \
    timeout "${CC_TIMEOUT:-1200}" claude -p "$PROMPT" \
      --mcp-config "$OUT/.mcp.json" \
      --allowedTools "mcp__axis__run" \
      --disallowedTools "Task,Agent,Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,WebFetch,WebSearch,Skill" \
      --output-format stream-json --verbose > "$OUT/claude_transcript.txt" 2>"$OUT/claude_cc.err" || true
  # Did Claude Code actually emit tool calls? If not, fall through to the probe.
  if ! grep -q 'mcp__axis__run' "$OUT/claude_transcript.txt" 2>/dev/null; then
    log "NOTE: Claude Code did not emit tool calls (local model limitation); adding scripted probe turns"
    RUN_CC=2   # marker: also run the probe so the deliverable has tool events
  fi
fi

if [ "$RUN_CC" != "1" ]; then
  log "=== driver: scripted probe (deterministic multi-turn) ==="
  : > "$OUT/probe_transcript.txt"
  # The client-side Lemonade serves the OpenAI API; the proxy forwards it
  # byte-for-byte. We send a real chat/completions call per turn so the inference
  # plane records real tokens + GPU consumption, then a tool call in that turn.
  INFER="http://127.0.0.1:$PROXY_PORT/api/v1/chat/completions"
  # Turn 0: a user prompt (new trace) + a tool call in that turn.
  curl -s --max-time 180 "$INFER" -H 'content-type: application/json' \
    -d "{\"model\":\"$LEMON_MODEL\",\"max_tokens\":32,\"messages\":[{\"role\":\"user\",\"content\":\"Turn 1: reply with exactly STEP1_OK\"}]}" \
    >> "$OUT/probe_transcript.txt" 2>/dev/null; echo >> "$OUT/probe_transcript.txt"
  node "$PROBE" "$SERVER" 'uname -a && echo STEP1_OK' >> "$OUT/probe_transcript.txt" 2>&1
  # Turn 1: a NEW user prompt (new trace) + a tool call in that turn.
  curl -s --max-time 180 "$INFER" -H 'content-type: application/json' \
    -d "{\"model\":\"$LEMON_MODEL\",\"max_tokens\":32,\"messages\":[{\"role\":\"user\",\"content\":\"Turn 2: reply with exactly STEP2_OK\"}]}" \
    >> "$OUT/probe_transcript.txt" 2>/dev/null; echo >> "$OUT/probe_transcript.txt"
  node "$PROBE" "$SERVER" 'echo STEP2_OK && hostname' >> "$OUT/probe_transcript.txt" 2>&1
  [ -f "$OUT/claude_transcript.txt" ] || echo "(no Claude Code transcript; scripted probe used)" > "$OUT/claude_transcript.txt"
fi

# --- 6. let the proxy flush its session_end -------------------------------
sleep 1

# --- 6b. optional: also ship the capture to a REAL Splunk HEC --------------
# The self-contained capture above uses the bundled fake HEC. If a real Splunk
# HEC is provided (REAL_SPLUNK_HEC_URL + REAL_SPLUNK_HEC_TOKEN), replay the same
# events into it so the deliverable proves real-Splunk ingestion/search too.
if [ -n "${REAL_SPLUNK_HEC_URL:-}" ] && [ -n "${REAL_SPLUNK_HEC_TOKEN:-}" ]; then
  log "shipping capture to real Splunk HEC at $REAL_SPLUNK_HEC_URL"
  shipped=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    env=$(printf '%s' "$line" | python3 -c "import sys,json;e=json.load(sys.stdin);st='axis:llm' if e.get('event','').startswith('llm') else 'axis:toolcall';print(json.dumps({'time':e.get('time'),'sourcetype':st,'index':'axis','event':e}))" 2>/dev/null) || continue
    curl -sk "${REAL_SPLUNK_HEC_URL%/}/services/collector/event" \
      -H "Authorization: Splunk $REAL_SPLUNK_HEC_TOKEN" -d "$env" >/dev/null 2>&1 && shipped=$((shipped+1))
  done < "$HEC_CAP"
  log "shipped $shipped events to real Splunk"
  REAL_SPLUNK_SHIPPED="$shipped"
fi

# --- 7. build the human-readable per-trace view + docs --------------------
log "assembling deliverable in $OUT"
python3 "$HERE/scripts/group_by_trace.py" "$HEC_CAP" > "$OUT/by_trace.md" 2>"$OUT/group.err" \
  || log "WARN: group_by_trace.py failed (see group.err)"

# session metadata
{
  echo "session_id: $SESS"
  echo "captured_utc: $TS"
  echo "host: $(hostname)"
  echo "driver: $([ "$RUN_CC" = "1" ] && echo claude-code || ([ "$RUN_CC" = "2" ] && echo "claude-code+scripted-probe" || echo "scripted-probe"))"
  echo "lemonade_model: $LEMON_MODEL"
  echo "event_count: $(wc -l < "$HEC_CAP" 2>/dev/null || echo 0)"
  echo "distinct_traces: $(python3 -c "import json,sys;print(len({json.loads(l).get('trace_id') for l in open('$HEC_CAP') if l.strip() and json.loads(l).get('trace_id')}))" 2>/dev/null || echo '?')"
  [ -n "${REAL_SPLUNK_SHIPPED:-}" ] && echo "real_splunk_shipped: $REAL_SPLUNK_SHIPPED"
} > "$OUT/session_meta.txt"

cp "$HERE/TELEMETRY_CONTRACT.md" "$OUT/SCHEMA.md" 2>/dev/null || true

cat > "$OUT/README.md" <<EOF
# AMD client-side agent session — telemetry capture for Cisco

Captured $TS on \`$(hostname)\` (Strix Halo deskside). One agent session
(\`identity.session=$SESS\`) driven through the two-plane governance loop:

- **inference plane** — Claude Code → Lemonade telemetry proxy → local Lemonade
  (Qwen3 on the AMD APU). Emits \`llm.request\` events.
- **tool/audit plane** — Claude Code → axis MCP connector → DefenseClaw admission
  → AXIS sandbox. Emits \`axis.toolcall\` events.

Both planes ship OTEL-shaped events to Splunk HEC (\`index=axis\`), correlated by
\`identity.session\` and grouped into per-turn **traces**.

## Files
- \`events.ndjson\` — every HEC event, both planes, newline-delimited JSON. The raw record.
- \`by_trace.md\` — the same events grouped the way Cisco defined a trace: one user
  prompt + all its LLM calls + all its tool calls = one \`trace_id\`. One session
  has multiple traces (one per turn).
- \`claude_transcript.txt\` — the agent driver transcript (stream-json).
- \`session_meta.txt\` — session id, host, event/trace counts.
- \`SCHEMA.md\` — the full telemetry field contract (OTEL mapping, GPU block, trace model).

## The three deltas from the meeting, visible here
1. **GPU consumption** — each local-tier \`llm.request\` carries a \`gpu\` block
   (\`busy_percent\`, \`vram_used_bytes\`, \`power_w\`, \`power_avg_w\`,
   \`energy_joules\`, \`temp_c\`, \`sclk_mhz\`) read from the AMD APU.
2. **OTEL shape** — every event has \`event_id\`, \`schema_version\`,
   \`ingest_source\`, \`trace_id\`/\`span_id\`/\`parent_span_id\`, a \`resource\`
   block (\`service.*\`), and (on \`llm.request\`) GenAI \`attributes\`
   (\`gen_ai.request.model\`, \`gen_ai.usage.*\`, \`gen_ai.provider.name\`,
   \`execution_location\`).
3. **Per-turn trace_id** — a new user prompt starts a new \`trace_id\`; the LLM
   calls and tool calls it triggers share it (see \`by_trace.md\`).
EOF

# --- 8. package -----------------------------------------------------------
( cd "$HERE/artifacts" && tar czf "cisco_session_$TS.tgz" "cisco_session_$TS" )
log "DONE: $OUT"
log "tarball: $HERE/artifacts/cisco_session_$TS.tgz"
cat "$OUT/session_meta.txt"
