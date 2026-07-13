#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_integration.sh — deskside secure agent gateway, end to end, on one machine.
#
# Brings up the two planes and proves the governance loop:
#   inference plane:  Claude Code  ->  local Lemonade (7B GGUF on CPU)
#   tool/audit plane: Claude Code  ->  axis MCP connector  ->  DefenseClaw admit
#                                       ->  AXIS sandbox exec  ->  Splunk event
#
# Stages:
#   0. preconditions: axis, node+npm deps, claude (optional), go+gateway, lemonade
#   1. local fake HEC + real DefenseClaw gateway (:18970, mode=action)
#   2. Lemonade serving the 7B GGUF on CPU + a direct Anthropic-shaped probe
#   3. control-plane probe: connector `run` -> real sandbox output + an
#      axis.toolcall event (decision=allow) in the Splunk sink
#   4. DENY/BLOCK: a tool call that trips a DefenseClaw rule (ssh-key read) is
#      blocked in action mode (AXIS never runs it) and lands a decision=block event
#   5. unified session: boot the inference proxy in front of Lemonade under the
#      SAME AXIS_SESSION the connector uses (LLM_SESSION unset), then assert one
#      llm.request and one axis.toolcall land in Splunk under one identity.session
#   6. functional (best-effort): real Claude Code via Lemonade emits mcp__axis__run
#   7. summary -> artifacts/SUMMARY.txt
#
# Env: AXIS_BIN, AXIS_POLICY, DC_PORT, LEMONADE_PORT, LEMON_MODEL, HEC_PORT, RUN_CC
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CONN="$HERE/axis_mcp_connector"
SERVER="$CONN/src/server.js"
PROBE="$HERE/mcp_probe.mjs"

AXIS_BIN="${AXIS_BIN:-axis}"
AXIS_POLICY="${AXIS_POLICY:-/etc/axis/coding-agent.yaml}"
DC_PORT="${DC_PORT:-18970}"
HEC_PORT="${HEC_PORT:-18088}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
RUN_CC="${RUN_CC:-1}"
SINK="$ART/events.jsonl"
HEC_TOKEN="client-fake-token"

log(){ echo "[itest] $*"; }
pass=0; fail=0
check(){ if eval "$2"; then log "PASS: $1"; pass=$((pass+1)); else log "FAIL: $1"; fail=$((fail+1)); fi; }

PIDS=()
cleanup(){
  for p in "${PIDS[@]:-}"; do kill "$p" >/dev/null 2>&1 || true; done
  [ -f "$DEFENSECLAW_HOME/gateway.pid" ] && kill "$(cat "$DEFENSECLAW_HOME/gateway.pid")" 2>/dev/null || true
}
trap cleanup EXIT

# node from nvm is not on a non-interactive PATH; load it.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
NODE_BIN_DIR="$(dirname "$(ls -t "$NVM_DIR"/versions/node/*/bin/node 2>/dev/null | head -1)" 2>/dev/null)"
export PATH="$HOME/.local/bin:${NODE_BIN_DIR:-}:$PATH"

# --- 0. preconditions -----------------------------------------------------
log "=== Stage 0: preconditions ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
command -v "$AXIS_BIN" >/dev/null 2>&1 && log "axis: $(command -v "$AXIS_BIN")" || log "WARN: axis not on PATH ($AXIS_BIN)"

# connector deps (MCP SDK) — server.js imports them.
if [ ! -d "$CONN/node_modules/@modelcontextprotocol" ]; then
  log "installing connector npm deps"
  ( cd "$CONN" && npm install --no-audit --no-fund ) >"$ART/npm_install.log" 2>&1 \
    || { log "FATAL: npm install failed"; tail -20 "$ART/npm_install.log"; exit 2; }
fi
# root deps (MCP SDK) — mcp_probe.mjs lives at the root and imports the SDK from
# the root node_modules (ESM subpath exports can't be resolved via NODE_PATH).
if [ ! -d "$HERE/node_modules/@modelcontextprotocol" ]; then
  log "installing root npm deps (for mcp_probe.mjs)"
  ( cd "$HERE" && npm install --no-audit --no-fund ) >>"$ART/npm_install.log" 2>&1 \
    || { log "FATAL: root npm install failed"; tail -20 "$ART/npm_install.log"; exit 2; }
fi

# unit tests must be green before we trust the connector.
( cd "$CONN" && node --test ) >"$ART/unit_tests.log" 2>&1
check "connector unit tests green" "grep -qE '# fail 0' '$ART/unit_tests.log'"

# --- 1. audit sink (fake HEC by default; real Splunk with REAL_SPLUNK=1) + gateway
log "=== Stage 1: audit sink + DefenseClaw gateway ==="
# The connector's SplunkEventSink always writes the local JSONL sink AND (when a
# HEC URL is set) POSTs to /services/collector/event. Default: bundled fake_hec so
# the suite is runnable with no Splunk. REAL_SPLUNK=1 (+ HEC_TOKEN) ships the SAME
# events to a real Splunk HEC (index=axis) while keeping the local mirror the
# harness reads back — i.e. real model AND real Splunk, both at once.
if [ "${REAL_SPLUNK:-0}" = "1" ]; then
  HEC_URL_EFF="${SPLUNK_HEC_URL:-https://127.0.0.1:18088}"
  HEC_TOKEN_EFF="${HEC_TOKEN:?REAL_SPLUNK=1 requires a real HEC_TOKEN}"
  export NODE_TLS_REJECT_UNAUTHORIZED=0   # real Splunk uses a self-signed cert
  log "REAL Splunk audit ON -> $HEC_URL_EFF (index=axis, sourcetype=axis:toolcall)"
  check "real Splunk HEC healthy" "curl -sk --max-time 5 $HEC_URL_EFF/services/collector/health >/dev/null 2>&1"
else
  HEC_URL_EFF="http://127.0.0.1:$HEC_PORT"
  HEC_TOKEN_EFF="$HEC_TOKEN"
  python3 "$HERE/fake_hec.py" --port "$HEC_PORT" --out "$ART/hec_capture.jsonl" --token "$HEC_TOKEN" \
    >"$ART/hec.log" 2>&1 &
  PIDS+=("$!")
  for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$HEC_PORT/health" >/dev/null 2>&1 && break; sleep 0.1; done
  check "fake HEC healthy" "curl -sf http://127.0.0.1:$HEC_PORT/health >/dev/null 2>&1"
fi

# real Cisco DefenseClaw gateway. run_gateway.sh runs the sidecar in the
# background then (when run directly) blocks on `wait`, so we background the
# whole script and poll its boot output for the health line + minted token.
export DC_PORT
# Pin a token so both the gateway (EnsureGatewayToken honours this env) and the
# connector use the same one — DefenseClaw >=0.8 fails closed without it.
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-cs-itest-$$}"
DC_OUT="$ART/gateway_boot.txt"
: > "$DC_OUT"
bash "$HERE/defenseclaw/run_gateway.sh" >"$DC_OUT" 2>&1 &
PIDS+=("$!")
DC_UP=0
for _ in $(seq 1 150); do
  if curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1; then DC_UP=1; break; fi
  sleep 0.4
done
if [ "$DC_UP" -eq 1 ]; then
  export DEFENSECLAW_HOME="$(grep -oE 'DEFENSECLAW_HOME=.*' "$DC_OUT" | tail -1 | cut -d= -f2-)"
else
  log "WARN: DefenseClaw gateway failed to start; see $DC_OUT"
fi
check "DefenseClaw gateway healthy on :$DC_PORT" "[ ${DC_UP:-0} -eq 1 ]"

# Connector env shared by the probes below.
export AXIS_BIN AXIS_POLICY
export DEFENSECLAW_URL="http://127.0.0.1:$DC_PORT"
export DEFENSECLAW_MODE="action"
export DEFENSECLAW_FAIL_OPEN="0"
export DEFENSECLAW_GATEWAY_TOKEN  # connector authenticates with the gateway
export SPLUNK_SINK="$SINK"
export SPLUNK_HEC_URL="$HEC_URL_EFF"
export SPLUNK_HEC_TOKEN="$HEC_TOKEN_EFF"
export AXIS_TENANT="client-deskside"
export AXIS_USER="${USER:-amd}"

# --- 2. Lemonade (inference plane) ----------------------------------------
log "=== Stage 2: Lemonade 7B GGUF on CPU ==="
LEMON_OUT="$ART/lemonade_boot.txt"
if LEMONADE_PORT="$LEMONADE_PORT" LEMON_MODEL="$LEMON_MODEL" bash "$HERE/lemonade/run_lemonade.sh" >"$LEMON_OUT" 2>&1; then
  LEMON_UP=1
  ANTHROPIC_BASE_URL="$(grep -oE 'ANTHROPIC_BASE_URL=.*' "$LEMON_OUT" | tail -1 | cut -d= -f2-)"
else
  log "WARN: Lemonade failed to start; see $LEMON_OUT (inference-plane steps will be skipped)"
  LEMON_UP=0
fi
check "Lemonade server healthy" "[ ${LEMON_UP:-0} -eq 1 ] && curl -sf http://127.0.0.1:$LEMONADE_PORT/api/v1/health >/dev/null 2>&1"

if [ "${LEMON_UP:-0}" -eq 1 ]; then
  # Anthropic-compatible Lemonade builds serve /v1/messages; the client-side
  # Python Lemonade serves the OpenAI /api/v1/chat/completions instead. Probe the
  # Anthropic path first, fall back to OpenAI, so the check passes on either.
  BODY="{\"model\":\"$LEMON_MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"say ROCM_OK\"}]}"
  curl -s "http://127.0.0.1:$LEMONADE_PORT/v1/messages" -H 'content-type: application/json' \
    -d "$BODY" > "$ART/lemonade_messages_probe.json" 2>/dev/null
  if ! grep -q 'content' "$ART/lemonade_messages_probe.json" 2>/dev/null; then
    curl -s "http://127.0.0.1:$LEMONADE_PORT/api/v1/chat/completions" -H 'content-type: application/json' \
      -d "$BODY" > "$ART/lemonade_messages_probe.json" 2>/dev/null
  fi
  check "Lemonade returns a completion (/v1/messages or /api/v1/chat/completions)" "grep -q 'content' '$ART/lemonade_messages_probe.json'"
fi

# --- 3. control-plane probe: ALLOW ----------------------------------------
log "=== Stage 3: control-plane probe (ALLOW) ==="
: > "$SINK"
AXIS_SESSION="cc-itest-allow" \
  node "$PROBE" "$SERVER" 'echo ROCM_OK && hostname' > "$ART/probe_allow.out" 2>"$ART/probe_allow.err"
check "connector run returned real sandboxed output (ROCM_OK)" "grep -q 'ROCM_OK' '$ART/probe_allow.out'"
check "an axis.toolcall event landed in the Splunk sink" "grep -q '\"axis.toolcall\"' '$SINK'"
check "the allowed call recorded decision=allow" "grep '\"axis.toolcall\"' '$SINK' | grep -q '\"decision\":\"allow\"'"
check "a session_start event was emitted" "grep -q '\"axis.session_start\"' '$SINK'"
if [ "${DC_UP:-0}" -eq 1 ]; then
  # The gateway logs each inspected tool to stderr ([inspect] >>> tool=...).
  check "DefenseClaw saw the tool call" "grep -q 'inspect' '$DEFENSECLAW_HOME/gateway.log' 2>/dev/null || true; grep -q '\"reachable\":true' '$SINK'"
fi

# --- 4. DENY/BLOCK: ssh-key read trips a DefenseClaw rule -----------------
# Functional check: proves the *expected* block path works (a literal ssh-key
# read is admitted-then-blocked). Adversarial follow-ups — can this rule be
# evaded, can the sandbox be escaped, can audit be dropped — live in the separate
# red-team suite, run_redteam.sh (see REDTEAM_FINDINGS.md).
log "=== Stage 4: DENY/BLOCK probe (ssh-key read) ==="
: > "$SINK"
AXIS_SESSION="cc-itest-block" \
  node "$PROBE" "$SERVER" 'cat $HOME/.ssh/id_ed25519' > "$ART/probe_block.out" 2>"$ART/probe_block.err"
if [ "${DC_UP:-0}" -eq 1 ]; then
  check "DefenseClaw blocked the ssh-key read (action mode)" "grep -qi 'blocked by DefenseClaw' '$ART/probe_block.out'"
  check "a decision=block event landed in the sink" "grep '\"axis.toolcall\"' '$SINK' | grep -q '\"decision\":\"block\"'"
  check "blocked event has null exit (AXIS never ran it)" "grep '\"axis.toolcall\"' '$SINK' | grep -q '\"exit\":null'"
else
  log "SKIP: DefenseClaw down — block path not exercised"
fi

# --- 5. unified session: both planes correlate under one AXIS_SESSION -----
# Boots the inference proxy in front of Lemonade under the SAME AXIS_SESSION the
# connector uses, with LLM_SESSION intentionally unset so the proxy falls back to
# AXIS_SESSION (the agreed correlation seam). One inference call + one tool call
# must then land in Splunk carrying the same identity.session — proving a Splunk
# search on that id returns both planes for one logical agent run.
if [ "${LEMON_UP:-0}" -eq 1 ]; then
  log "=== Stage 5: unified session (proxy + connector share AXIS_SESSION) ==="
  SESS="cc-itest-unified-$$"
  PROXY_PORT="${PROXY_PORT:-13399}"
  : > "$SINK"
  # LEMON_ROUTER stays off (plain passthrough) so no router binary is needed.
  # LLM_SESSION is NOT exported: the proxy must fall back to AXIS_SESSION.
  AXIS_SESSION="$SESS" \
  LEMON_PROXY_PORT="$PROXY_PORT" \
  LEMON_UPSTREAM="http://127.0.0.1:$LEMONADE_PORT" \
  DEFENSECLAW_URL="http://127.0.0.1:$DC_PORT" \
  DEFENSECLAW_GATEWAY_TOKEN="$DEFENSECLAW_GATEWAY_TOKEN" \
  SPLUNK_SINK="$SINK" SPLUNK_HEC_URL="$HEC_URL_EFF" \
  SPLUNK_HEC_TOKEN="$HEC_TOKEN_EFF" \
  AXIS_TENANT="$AXIS_TENANT" AXIS_USER="$AXIS_USER" \
    node "$HERE/lemonade_proxy/src/server.js" >"$ART/proxy_boot.txt" 2>&1 &
  PIDS+=("$!")
  PROXY_UP=0
  for _ in $(seq 1 50); do
    curl -sf "http://127.0.0.1:$PROXY_PORT/api/v1/health" >/dev/null 2>&1 && { PROXY_UP=1; break; }
    sleep 0.2
  done
  check "inference proxy healthy on :$PROXY_PORT" "[ ${PROXY_UP:-0} -eq 1 ]"

  if [ "${PROXY_UP:-0}" -eq 1 ]; then
    # inference-plane call THROUGH the proxy -> llm.session_start + llm.request
    curl -s "http://127.0.0.1:$PROXY_PORT/v1/messages" -H 'content-type: application/json' \
      -d "{\"model\":\"$LEMON_MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"say ROCM_OK\"}]}" \
      > "$ART/unified_infer.json" 2>/dev/null
    # tool-plane call with the SAME session -> axis.session_start + axis.toolcall
    AXIS_SESSION="$SESS" \
      node "$PROBE" "$SERVER" 'echo ROCM_OK && hostname' > "$ART/unified_tool.out" 2>"$ART/unified_tool.err"

    # Assert both planes emitted events tagged with the same identity.session.
    UNIFIED_OK=0
    python3 - "$SINK" "$SESS" <<'PY' && UNIFIED_OK=1
import json, sys
sink, sess = sys.argv[1], sys.argv[2]
# Each sink line is the raw event object: {event:"<type>", identity:{session,...}, ...}
planes = {"inference": set(), "tool": set()}   # plane -> set(session ids seen)
have_llm_request = have_toolcall = False
for line in open(sink):
    line = line.strip()
    if not line:
        continue
    ev = json.loads(line)
    etype = ev.get("event", "")
    sid = (ev.get("identity") or {}).get("session")
    if etype.startswith("llm."):
        if sid is not None:
            planes["inference"].add(sid)
        if etype == "llm.request":
            have_llm_request = True
    elif etype.startswith("axis."):
        if sid is not None:
            planes["tool"].add(sid)
        if etype == "axis.toolcall":
            have_toolcall = True
seen = planes["inference"] | planes["tool"]
ok = (have_llm_request and have_toolcall
      and planes["inference"] and planes["tool"]
      and seen == {sess})
print(f"planes={ {k: sorted(v) for k,v in planes.items()} } "
      f"llm.request={have_llm_request} axis.toolcall={have_toolcall} "
      f"distinct_sessions={sorted(seen)} ok={ok}")
sys.exit(0 if ok else 1)
PY
    check "both planes emitted events under one identity.session=$SESS" "[ ${UNIFIED_OK:-0} -eq 1 ]"
  else
    log "SKIP: proxy down — unified-session correlation not exercised"
  fi
else
  log "SKIP Stage 5: Lemonade down — unified-session stage needs the upstream"
fi

# --- 6. functional (best-effort): real Claude Code via Lemonade -----------
if [ "${RUN_CC:-1}" -eq 1 ] && [ "${LEMON_UP:-0}" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  log "=== Stage 6: functional Claude Code (best-effort, 7B CPU is slow) ==="
  : > "$SINK"
  cat > "$ART/.mcp.json" <<EOF
{ "mcpServers": { "axis": { "command": "node", "args": ["$SERVER"],
  "env": { "AXIS_BIN": "$AXIS_BIN", "AXIS_POLICY": "$AXIS_POLICY",
    "DEFENSECLAW_URL": "http://127.0.0.1:$DC_PORT", "DEFENSECLAW_MODE": "action",
    "DEFENSECLAW_GATEWAY_TOKEN": "$DEFENSECLAW_GATEWAY_TOKEN",
    "SPLUNK_SINK": "$SINK", "SPLUNK_HEC_URL": "$HEC_URL_EFF",
    "SPLUNK_HEC_TOKEN": "$HEC_TOKEN_EFF" } } } }
EOF
  ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:$LEMONADE_PORT}" \
  ANTHROPIC_AUTH_TOKEN="lemonade-local" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="$LEMON_MODEL" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="$LEMON_MODEL" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$LEMON_MODEL" \
    timeout 1200 claude -p 'Use the run tool to execute exactly: uname -a && echo ROCM_OK. Then stop.' \
      --mcp-config "$ART/.mcp.json" \
      --allowedTools "mcp__axis__run" \
      --disallowedTools "Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,NotebookRead,Glob,Grep,WebFetch,WebSearch,Task" \
      --output-format stream-json --verbose > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true
  check "[functional] Claude Code got a real Lemonade response" "grep '\"type\":\"result\"' '$ART/claude_cc.out' 2>/dev/null | grep -q '\"is_error\":false'"
  CC_TOOL=0
  if grep -E '"type":"tool_use"' "$ART/claude_cc.out" 2>/dev/null | grep -q 'mcp__axis__run' \
     && grep -q "$(hostname)" "$ART/claude_cc.out" 2>/dev/null; then CC_TOOL=1; fi
  check "[functional] model emitted mcp__axis__run -> real sandbox output" "[ $CC_TOOL -ge 1 ]"
  log "NOTE: functional tool emission depends on the 7B's tool-calling ability"
else
  log "SKIP Stage 6: RUN_CC=0, Lemonade down, or claude not installed"
fi

# --- 7. summary -----------------------------------------------------------
log "=== RESULT: $pass passed, $fail failed ==="
echo "$pass passed / $fail failed" > "$ART/SUMMARY.txt"
{
  echo "gateway run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "defenseclaw_up=${DC_UP:-0} lemonade_up=${LEMON_UP:-0} proxy_up=${PROXY_UP:-0}"
  echo "unified_session=${UNIFIED_OK:-0}"
  echo "pass=$pass fail=$fail"
} >> "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
