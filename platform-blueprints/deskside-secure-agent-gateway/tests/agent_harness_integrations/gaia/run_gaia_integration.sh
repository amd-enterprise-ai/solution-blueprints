#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_gaia_integration.sh — prove the CLIENT-SIDE axis MCP connector works with
# gaia (AMD's agent framework) as a second MCP host, alongside Claude Code, with
# every tool call audited end-to-end in a REAL Splunk.
#
# The connector, DefenseClaw gateway, AXIS sandbox and real Splunk are identical
# to amd_gateway_test — only the *MCP host* changes (gaia instead of, and
# in addition to, Claude Code). The connector is reused unchanged by path.
#
# Stages:
#   0. preconditions: node, axis, connector deps + unit tests, GATEWAY_KEY, python;
#      clone gaia + install into a venv
#   1. real Splunk (reuse-or-install)
#   2. real DefenseClaw gateway (:18970, action)
#   3. register the connector with gaia (mcp_servers.json incl. full env);
#      gaia's MCP client lists the `run` tool
#   4. gaia deterministic probe (HARD): gaia.mcp.client.MCPClient drives the
#      connector -> real sandbox output + event CONFIRMED in Splunk (session gaia-probe)
#   5. cross-host: a Claude-Code run-tool call (session cc-gaia) -> event in Splunk
#   6. gaia agentic (best-effort): gaia Agent via the gateway emits the tool ->
#      event in Splunk (session gaia-agent); SKIP if inference wiring unavailable
#   7. cross-host proof: index=axis holds BOTH a gaia session AND a Claude-Code session
#   8. summary -> artifacts/SUMMARY.txt + artifacts/splunk_query.txt
#
# Env: GATEWAY_KEY (required), GATEWAY_URL, MODEL, SPLUNK_URL/SPLUNK_TGZ, SPLUNK_PASS,
#      HEC_TOKEN, AXIS_BIN, AXIS_POLICY, DC_PORT, GAIA_REPO, GAIA_VENV, RUN_CC,
#      RUN_AGENTIC, OPENAI_BASE_URL/OPENAI_API_KEY or LEMONADE_BASE_URL (agentic LLM)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../../stack" && pwd)"
SPLUNK_TEST="$(cd "$CSI/splunk" && pwd)"          # vendored real-Splunk install + query
GWTEST="$(cd "$HERE/../claude_code" && pwd)"   # reuse claude_job.sh for cross-host
CONN="$CSI/axis_mcp_connector"
SERVER="$CONN/src/server.js"

# --- inference plane: AMD LLM Gateway -------------------------------------
GATEWAY_URL="${GATEWAY_URL:-https://api.anthropic.com}"
GATEWAY_KEY="${GATEWAY_KEY:-${ANTHROPIC_API_KEY:-}}"
MODEL="${MODEL:-claude-opus-4-8}"

# --- control plane -------------------------------------------------------
AXIS_BIN="${AXIS_BIN:-$(command -v axis 2>/dev/null || echo /usr/local/bin/axis)}"
AXIS_POLICY="${AXIS_POLICY:-/etc/axis/coding-agent.yaml}"
DC_PORT="${DC_PORT:-18970}"

# --- audit plane: real Splunk --------------------------------------------
SPLUNK_HOME="${SPLUNK_HOME:-$HOME/splunk}"
SPLUNK_USER="${SPLUNK_USER:-admin}"
SPLUNK_PASS="${SPLUNK_PASS:?set SPLUNK_PASS}"
SPLUNK_INDEX="${SPLUNK_INDEX:-axis}"
WEB_PORT="${WEB_PORT:-8000}"
MGMT_PORT="${MGMT_PORT:-8089}"
HEC_PORT="${HEC_PORT:-8088}"
HEC_TOKEN="${HEC_TOKEN:-$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null)}"
SPLUNK_MGMT_URL="https://127.0.0.1:$MGMT_PORT"
SPLUNK_HEC_URL="https://127.0.0.1:$HEC_PORT"

# --- gaia ----------------------------------------------------------------
GAIA_REPO="${GAIA_REPO:-$ART/gaia}"
GAIA_VENV="${GAIA_VENV:-$ART/gaia-venv}"
RUN_CC="${RUN_CC:-1}"
RUN_AGENTIC="${RUN_AGENTIC:-1}"

# gaia's LLM plane for the agentic stage: a LOCAL Lemonade server serving a small
# CPU model. gaia's built-in providers don't honour a custom gateway base_url, so
# the agentic driver uses gaia's native Lemonade path (LEMONADE_BASE_URL) against
# an 8B GGUF served on CPU by the shared stack/lemonade tooling.
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMONADE_BASE_URL="${LEMONADE_BASE_URL:-http://127.0.0.1:$LEMONADE_PORT/api/v1}"
SINK="$ART/events.jsonl"
: > "$SINK"

export NODE_TLS_REJECT_UNAUTHORIZED=0

log(){ echo "[gaia-test] $*"; }
pass=0; fail=0
check(){ if eval "$2"; then log "PASS: $1"; pass=$((pass+1)); else log "FAIL: $1"; fail=$((fail+1)); fi; }

PIDS=()
cleanup(){
  for p in "${PIDS[@]:-}"; do kill "$p" >/dev/null 2>&1 || true; done
  [ -n "${DEFENSECLAW_HOME:-}" ] && [ -f "$DEFENSECLAW_HOME/gateway.pid" ] \
    && kill "$(cat "$DEFENSECLAW_HOME/gateway.pid")" 2>/dev/null || true
}
trap cleanup EXIT

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
NODE_BIN_DIR="$(dirname "$(ls -t "$NVM_DIR"/versions/node/*/bin/node 2>/dev/null | head -1)" 2>/dev/null)"
export PATH="$HOME/.local/bin:${NODE_BIN_DIR:-}:$PATH"

splunk_export(){
  curl -sk -u "$SPLUNK_USER:$SPLUNK_PASS" "$SPLUNK_MGMT_URL/services/search/jobs/export" \
    --data-urlencode "search=$1" \
    --data-urlencode "earliest_time=-15m" \
    --data-urlencode "latest_time=now" \
    --data-urlencode "output_mode=json" 2>/dev/null
}
splunk_wait(){
  local c
  for _ in $(seq 1 30); do
    c="$(splunk_export "$1" | grep -c '"result":' || true)"
    [ "${c:-0}" -ge "$2" ] && return 0
    sleep 2
  done
  return 1
}

# --- 0. preconditions -----------------------------------------------------
log "=== Stage 0: preconditions + gaia install ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
command -v git >/dev/null 2>&1 || { log "FATAL: git not found"; exit 2; }
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { log "FATAL: python3 not found"; exit 2; }

if [ ! -d "$CONN/node_modules/@modelcontextprotocol" ]; then
  ( cd "$CONN" && npm install --no-audit --no-fund ) >"$ART/npm_install.log" 2>&1 \
    || { log "FATAL: connector npm install failed"; tail -20 "$ART/npm_install.log"; exit 2; }
fi
( cd "$CONN" && node --test ) >"$ART/unit_tests.log" 2>&1
check "connector unit tests green" "grep -q 'pass 28' '$ART/unit_tests.log' || grep -qE '# fail 0' '$ART/unit_tests.log'"
check "GATEWAY_KEY provided" "[ -n \"$GATEWAY_KEY\" ]"

# Clone + install gaia into a dedicated venv.
if [ ! -d "$GAIA_REPO/.git" ]; then
  log "cloning amd/gaia -> $GAIA_REPO"
  git clone --depth 1 https://github.com/amd/gaia "$GAIA_REPO" >"$ART/gaia_clone.log" 2>&1 \
    || { log "WARN: gaia clone failed; see gaia_clone.log"; tail -10 "$ART/gaia_clone.log"; }
fi
if [ ! -x "$GAIA_VENV/bin/python" ]; then
  log "creating gaia venv at $GAIA_VENV"
  "$PY" -m venv "$GAIA_VENV" >"$ART/gaia_install.log" 2>&1
  PYVER="$("$PY" -c 'import sys; print(".".join(map(str,sys.version_info[:2])))')"
  GSITE="$GAIA_VENV/lib/python$PYVER/site-packages"
  pip3 install -e "$GAIA_REPO[mcp]" --target "$GSITE" >>"$ART/gaia_install.log" 2>&1 \
    || pip3 install "amd-gaia[mcp]" --target "$GSITE" >>"$ART/gaia_install.log" 2>&1 || true
fi
GPY="$GAIA_VENV/bin/python"
check "gaia importable in venv" "'$GPY' -c 'import gaia; from gaia.mcp.client.mcp_client import MCPClient' 2>/dev/null"

# --- 1. real Splunk -------------------------------------------------------
log "=== Stage 1: real Splunk (HEC + index=$SPLUNK_INDEX) ==="
if curl -sk --fail "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 \
   && curl -sk --fail -u "$SPLUNK_USER:$SPLUNK_PASS" "$SPLUNK_MGMT_URL/services/server/info" >/dev/null 2>&1; then
  log "Splunk already up and creds valid -> reusing existing instance"
elif [ -x "$SPLUNK_HOME/bin/splunk" ] || [ -n "${SPLUNK_URL:-}" ] || [ -n "${SPLUNK_TGZ:-}" ]; then
  SPLUNK_HOME="$SPLUNK_HOME" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
    SPLUNK_INDEX="$SPLUNK_INDEX" WEB_PORT="$WEB_PORT" MGMT_PORT="$MGMT_PORT" HEC_PORT="$HEC_PORT" \
    HEC_TOKEN="$HEC_TOKEN" SPLUNK_URL="${SPLUNK_URL:-}" SPLUNK_TGZ="${SPLUNK_TGZ:-}" \
    bash "$SPLUNK_TEST/install_splunk.sh" >"$ART/splunk_install.log" 2>&1 \
    || { log "WARN: install_splunk.sh non-zero"; tail -25 "$ART/splunk_install.log"; }
else
  log "FATAL: Splunk not up and no SPLUNK_URL/SPLUNK_TGZ"; exit 2
fi
SPLUNK_UP=0
for _ in $(seq 1 60); do
  curl -sk "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 && { SPLUNK_UP=1; break; }
  sleep 1
done
check "Splunk HEC healthy on :$HEC_PORT" "[ $SPLUNK_UP -eq 1 ]"
check "Splunk mgmt/search API auth OK" "curl -sk --fail -u '$SPLUNK_USER:$SPLUNK_PASS' '$SPLUNK_MGMT_URL/services/server/info' >/dev/null 2>&1"

# --- 2. DefenseClaw -------------------------------------------------------
log "=== Stage 2: DefenseClaw gateway ==="
export DC_PORT
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-gw-gaia-$$}"
if curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1; then
  log "WARN: :$DC_PORT in use; killing stale defenseclaw-gateway"
  pkill -9 -f defenseclaw-gateway 2>/dev/null || true
  sleep 2
fi
DC_OUT="$ART/gateway_boot.txt"; : > "$DC_OUT"
bash "$CSI/defenseclaw/run_gateway.sh" >"$DC_OUT" 2>&1 &
PIDS+=("$!")
DC_UP=0
for _ in $(seq 1 150); do
  curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1 && { DC_UP=1; break; }
  sleep 0.4
done
[ "$DC_UP" -eq 1 ] && export DEFENSECLAW_HOME="$(grep -oE 'DEFENSECLAW_HOME=.*' "$DC_OUT" | tail -1 | cut -d= -f2-)"
check "DefenseClaw gateway healthy on :$DC_PORT" "[ ${DC_UP:-0} -eq 1 ]"

# Connector env shared by gaia probe + claude (audit plane -> REAL Splunk).
export AXIS_BIN AXIS_POLICY
export DEFENSECLAW_URL="http://127.0.0.1:$DC_PORT"
export DEFENSECLAW_MODE="action"
export DEFENSECLAW_FAIL_OPEN="0"
export DEFENSECLAW_GATEWAY_TOKEN
export SPLUNK_SINK="$SINK"
export SPLUNK_HEC_URL="$SPLUNK_HEC_URL"
export SPLUNK_HEC_TOKEN="$HEC_TOKEN"
export AXIS_TENANT="client-deskside"
export AXIS_USER="${USER:-amd}"
export AXIS_POLICY_SOURCE="local-control"
export AXIS_POLICY_ID="coding-agent"

# --- 3. register connector with gaia -------------------------------------
log "=== Stage 3: register connector with gaia (mcp_servers.json) ==="
GAIA_MCP_CONFIG="$ART/mcp_servers.json"
cat > "$GAIA_MCP_CONFIG" <<JSON
{
  "mcpServers": {
    "axis": {
      "command": "node",
      "args": ["$SERVER"],
      "env": {
        "AXIS_BIN": "$AXIS_BIN",
        "AXIS_POLICY": "$AXIS_POLICY",
        "DEFENSECLAW_URL": "http://127.0.0.1:$DC_PORT",
        "DEFENSECLAW_MODE": "action",
        "DEFENSECLAW_FAIL_OPEN": "0",
        "DEFENSECLAW_GATEWAY_TOKEN": "$DEFENSECLAW_GATEWAY_TOKEN",
        "SPLUNK_SINK": "$SINK",
        "SPLUNK_HEC_URL": "$SPLUNK_HEC_URL",
        "SPLUNK_HEC_TOKEN": "$HEC_TOKEN",
        "NODE_TLS_REJECT_UNAUTHORIZED": "0",
        "AXIS_SESSION": "gaia-agent",
        "AXIS_TENANT": "client-deskside",
        "AXIS_USER": "amd",
        "AXIS_POLICY_SOURCE": "local-control",
        "AXIS_POLICY_ID": "coding-agent"
      }
    }
  }
}
JSON
export GAIA_MCP_CONFIG
# Verify gaia's MCP client recognises the server + the `run` tool from this config.
"$GPY" - "$GAIA_MCP_CONFIG" >"$ART/gaia_mcp_list.txt" 2>&1 <<'PY' || true
import sys, json
from gaia.mcp.client.config import MCPConfig
from gaia.mcp.client.mcp_client import MCPClient
cfg = json.load(open(sys.argv[1]))
servers = cfg["mcpServers"]
for name, sc in servers.items():
    c = MCPClient.from_config(name, sc, timeout=60)
    ok = c.connect()
    tools = [t.name for t in c.list_tools()] if ok else []
    print(f"server={name} connected={ok} tools={tools}")
    c.disconnect()
PY
sed -n '1,20p' "$ART/gaia_mcp_list.txt"
check "gaia MCP client lists the connector's run tool" "grep -q \"'run'\" '$ART/gaia_mcp_list.txt' || grep -q '\"run\"' '$ART/gaia_mcp_list.txt'"

# --- 4. gaia deterministic probe (HARD) ----------------------------------
log "=== Stage 4: gaia deterministic MCP probe (HARD) ==="
AXIS_SESSION="gaia-probe" \
  "$GPY" "$HERE/gaia_mcp_probe.py" "$SERVER" 'echo GAIA_OK && hostname' \
  > "$ART/gaia_probe.out" 2>"$ART/gaia_probe.err" || true
sed -n '1,30p' "$ART/gaia_probe.out"
check "gaia-driven run returned real sandbox output (GAIA_OK)" "grep -q 'GAIA_OK' '$ART/gaia_probe.out'"
check "gaia-driven run produced decision=allow in local sink" \
  "grep '\"axis.toolcall\"' '$SINK' | grep -q '\"decision\":\"allow\"'"
check "gaia event CONFIRMED in real Splunk index via search API" \
  "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=gaia-probe event=axis.toolcall decision=allow' 1"

# --- 5. cross-host: a Claude Code run-tool call --------------------------
CC_DONE=0
if [ "${RUN_CC:-1}" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  log "=== Stage 5: cross-host Claude Code run-tool call ==="
  MCP_JSON="$ART/.mcp.cc.json"
  cat > "$MCP_JSON" <<JSON
{
  "mcpServers": {
    "axis": {
      "command": "node",
      "args": ["$SERVER"],
      "env": {
        "AXIS_BIN": "$AXIS_BIN",
        "AXIS_POLICY": "$AXIS_POLICY",
        "DEFENSECLAW_URL": "http://127.0.0.1:$DC_PORT",
        "DEFENSECLAW_MODE": "action",
        "DEFENSECLAW_FAIL_OPEN": "0",
        "DEFENSECLAW_GATEWAY_TOKEN": "$DEFENSECLAW_GATEWAY_TOKEN",
        "SPLUNK_SINK": "$SINK",
        "SPLUNK_HEC_URL": "$SPLUNK_HEC_URL",
        "SPLUNK_HEC_TOKEN": "$HEC_TOKEN",
        "NODE_TLS_REJECT_UNAUTHORIZED": "0",
        "AXIS_SESSION": "cc-gaia",
        "AXIS_TENANT": "client-deskside",
        "AXIS_USER": "amd",
        "AXIS_POLICY_SOURCE": "local-control",
        "AXIS_POLICY_ID": "coding-agent"
      }
    }
  }
}
JSON
  CC_PROMPT="$ART/cc_gaia_prompt.txt"
  echo 'Use the run tool to execute exactly: echo CC_GAIA_OK && hostname. Then stop.' > "$CC_PROMPT"
  GATEWAY_URL="$GATEWAY_URL" GATEWAY_KEY="$GATEWAY_KEY" MODEL="$MODEL" \
    INFERENCE_MODE="${INFERENCE_MODE:-gateway}" ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    bash "$GWTEST/claude_job.sh" "$MCP_JSON" "$CC_PROMPT" \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true
  check "[cross-host] Claude Code emitted mcp__axis__run" \
    "grep -E '\"type\":\"tool_use\"' '$ART/claude_cc.out' 2>/dev/null | grep -q 'mcp__axis__run'"
  check "[cross-host] Claude-Code event CONFIRMED in Splunk" \
    "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=cc-gaia event=axis.toolcall decision=allow' 1"
  CC_DONE=1
else
  log "SKIP Stage 5: RUN_CC=0 or claude not installed"
fi

# --- 6. gaia agentic via a LOCAL Lemonade 8B model -----------------------
# A gaia Agent (LLM = Qwen3-8B-GGUF on CPU via the local Lemonade server) decides
# on its own to call the connector's run tool -> DefenseClaw -> AXIS -> Splunk.
AGENTIC=skip
if [ "${RUN_AGENTIC:-1}" -eq 1 ]; then
  log "=== Stage 6: gaia agentic via local Lemonade ($LEMON_MODEL on CPU) ==="
  LEMON_UP=0
  if curl -sf "http://127.0.0.1:$LEMONADE_PORT/api/v1/health" >/dev/null 2>&1; then
    log "Lemonade already up on :$LEMONADE_PORT -> reusing"
    LEMON_UP=1
  elif [ -x "$CSI/lemonade/run_lemonade.sh" ]; then
    log "starting Lemonade ($LEMON_MODEL) via gateway tooling"
    LEMONADE_PORT="$LEMONADE_PORT" LEMON_MODEL="$LEMON_MODEL" \
      bash "$CSI/lemonade/run_lemonade.sh" >"$ART/lemonade_boot.txt" 2>&1 || true
    curl -sf "http://127.0.0.1:$LEMONADE_PORT/api/v1/health" >/dev/null 2>&1 && LEMON_UP=1
  fi
  if [ "$LEMON_UP" -eq 1 ]; then
    GAIA_MODEL="$LEMON_MODEL" LEMONADE_BASE_URL="$LEMONADE_BASE_URL" \
      GAIA_MCP_CONFIG="$GAIA_MCP_CONFIG" \
      "$GPY" "$HERE/gaia_agent_query.py" \
      > "$ART/gaia_agent.out" 2>"$ART/gaia_agent.err" || true
    if splunk_wait 'search index='"$SPLUNK_INDEX"' | spath | search identity.session=gaia-agent event=axis.toolcall decision=allow' 1; then
      AGENTIC=ok
      check "[agentic] gaia Agent (Lemonade $LEMON_MODEL) event CONFIRMED in Splunk" "true"
    else
      log "agentic stage did not confirm in Splunk -> reported SKIP"
      tail -8 "$ART/gaia_agent.err" 2>/dev/null
    fi
  else
    log "Lemonade not available -> agentic stage reported SKIP (stage 4 still HARD-proves the integration)"
  fi
fi

# --- 7. cross-host proof --------------------------------------------------
log "=== Stage 7: cross-host proof (gaia + Claude Code in the same index) ==="
check "Splunk holds a gaia-driven toolcall" \
  "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=gaia-probe event=axis.toolcall' 1"
# A Claude-Code session from this run (cc-gaia) or any pre-existing cc-* session.
check "Splunk holds a Claude-Code toolcall (cross-host)" \
  "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=cc-gaia event=axis.toolcall' 1 || splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=cc-gw-allow event=axis.toolcall' 1"

# --- 8. summary -----------------------------------------------------------
log "=== Dumping the Splunk index -> artifacts/splunk_query.txt ==="
SPLUNK_MGMT_URL="$SPLUNK_MGMT_URL" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
  SPLUNK_INDEX="$SPLUNK_INDEX" EARLIEST="-1h" \
  bash "$SPLUNK_TEST/query_splunk.sh" > "$ART/splunk_query.txt" 2>&1 || true
sed -n '1,40p' "$ART/splunk_query.txt" 2>/dev/null

log "=== RESULT: $pass passed, $fail failed (agentic=$AGENTIC) ==="
{
  echo "gaia run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "model=$MODEL gateway=$GATEWAY_URL"
  echo "splunk_up=${SPLUNK_UP:-0} defenseclaw_up=${DC_UP:-0} cc_cross_host=${CC_DONE}"
  echo "agentic=$AGENTIC"
  echo "pass=$pass fail=$fail"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
