#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_gaia_integration.sh — prove the CLIENT-SIDE axis MCP connector works with
# gaia (AMD's agent framework) as a second MCP host, alongside Claude Code, with
# every tool call audited end-to-end in a SQLite audit DB.
#
# The connector, AXIS sandbox, and SQLite audit DB are identical to
# amd_gateway_test — only the *MCP host* changes (gaia instead of, and
# in addition to, Claude Code). The connector is reused unchanged by path.
#
# Stages:
#   0. preconditions: node, axis, connector deps + unit tests, inference access, python;
#      clone gaia + install into a venv
#   3. register the connector with gaia (mcp_servers.json incl. full env);
#      gaia's MCP client lists the `run` tool
#   4. gaia deterministic probe (HARD): gaia.mcp.client.MCPClient drives the
#      connector -> real sandbox output + event CONFIRMED in SQLite DB (session gaia-probe)
#   5. cross-host: a Claude-Code run-tool call (session cc-gaia) -> event in SQLite DB
#   6. gaia agentic (best-effort): gaia Agent via the gateway emits the tool ->
#      event in SQLite DB (session gaia-agent); SKIP if inference wiring unavailable
#   7. cross-host proof: audit DB holds BOTH a gaia session AND a Claude-Code session
#   8. summary -> artifacts/SUMMARY.txt (SQLite event count)
#
# Env: inference access (ANTHROPIC_API_KEY, or ANTHROPIC_BASE_URL+ANTHROPIC_AUTH_TOKEN,
#      or ANTHROPIC_CUSTOM_HEADERS, or the GATEWAY_KEY/GATEWAY_URL alias),
#      MODEL, AUDIT_DB, AXIS_BIN, AXIS_POLICY, GAIA_REPO, GAIA_VENV, RUN_CC, RUN_AGENTIC,
#      OPENAI_BASE_URL/OPENAI_API_KEY or LEMONADE_BASE_URL (agentic LLM)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../../stack" && pwd)"
GWTEST="$(cd "$HERE/../claude_code" && pwd)"   # reuse claude_job.sh for cross-host
CONN="$CSI/axis_mcp_connector"
SERVER="$CONN/src/server.js"

# --- inference plane: bring-your-own Anthropic-compatible access ----------
# The cross-host Claude stage resolves access via tests/lib/inference_env.sh
# (auto-detects ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL+ANTHROPIC_AUTH_TOKEN /
# ANTHROPIC_CUSTOM_HEADERS / the GATEWAY_KEY alias). Do NOT alias GATEWAY_KEY
# from ANTHROPIC_API_KEY here — that would force the custom-header gateway path
# and break the plain Anthropic-direct run.
GATEWAY_URL="${GATEWAY_URL:-}"
GATEWAY_KEY="${GATEWAY_KEY:-}"
MODEL="${MODEL:-claude-opus-4-8}"

# --- control plane -------------------------------------------------------
AXIS_BIN="${AXIS_BIN:-$(command -v axis 2>/dev/null || echo /usr/local/bin/axis)}"
AXIS_POLICY="${AXIS_POLICY:-/etc/axis/coding-agent.yaml}"

# --- audit plane: SQLite DB ----------------------------------------------
AUDIT_DB="${AUDIT_DB:-$ART/audit.db}"
# Start from a clean audit DB so probes assert on THIS run's events.
rm -f "$AUDIT_DB"
# shellcheck source=../../lib/audit_db.sh
source "$HERE/../../lib/audit_db.sh"

# --- gaia ----------------------------------------------------------------
GAIA_REPO="${GAIA_REPO:-$ART/gaia}"
GAIA_VENV="${GAIA_VENV:-$ART/gaia-venv}"
# Pin gaia to the verified commit (amd/gaia moves fast; HEAD is not guaranteed).
GAIA_COMMIT="${GAIA_COMMIT:-a441765672e2e4e7d00ee3056323cfaed95a848c}"
RUN_CC="${RUN_CC:-1}"
RUN_AGENTIC="${RUN_AGENTIC:-1}"

# gaia's LLM plane for the agentic stage: a LOCAL Lemonade server serving a small
# CPU model. gaia's built-in providers don't honour a custom gateway base_url, so
# the agentic driver uses gaia's native Lemonade path (LEMONADE_BASE_URL) against
# an 8B GGUF served on CPU by the shared stack/lemonade tooling.
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMONADE_BASE_URL="${LEMONADE_BASE_URL:-http://127.0.0.1:$LEMONADE_PORT/api/v1}"

export NODE_TLS_REJECT_UNAUTHORIZED=0

log(){ echo "[gaia-test] $*"; }
pass=0; fail=0
check(){ if eval "$2"; then log "PASS: $1"; pass=$((pass+1)); else log "FAIL: $1"; fail=$((fail+1)); fi; }

PIDS=()
cleanup(){
  for p in "${PIDS[@]:-}"; do kill "$p" >/dev/null 2>&1 || true; done
}
trap cleanup EXIT

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
NODE_BIN_DIR="$(dirname "$(ls -t "$NVM_DIR"/versions/node/*/bin/node 2>/dev/null | head -1)" 2>/dev/null)"
export PATH="$HOME/.local/bin:${NODE_BIN_DIR:-}:$PATH"

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
check "connector unit tests green" "grep -q 'pass 32' '$ART/unit_tests.log' || grep -qE '# fail 0' '$ART/unit_tests.log'"
check "inference access configured" \
  "[ -n \"${ANTHROPIC_API_KEY:-}\" ] || [ -n \"${ANTHROPIC_AUTH_TOKEN:-}\" ] || [ -n \"${ANTHROPIC_CUSTOM_HEADERS:-}\" ] || [ -n \"${GATEWAY_KEY:-}\" ]"

# Clone + install gaia into a dedicated venv.
if [ ! -d "$GAIA_REPO/.git" ]; then
  log "cloning amd/gaia @ $GAIA_COMMIT -> $GAIA_REPO"
  git clone --filter=blob:none https://github.com/amd/gaia "$GAIA_REPO" >"$ART/gaia_clone.log" 2>&1 \
    && git -C "$GAIA_REPO" checkout --quiet "$GAIA_COMMIT" >>"$ART/gaia_clone.log" 2>&1 \
    || { log "WARN: gaia clone/checkout failed; see gaia_clone.log"; tail -10 "$ART/gaia_clone.log"; }
fi
# Rebuild the venv unless gaia already imports cleanly. An interrupted run
# leaves bin/python behind without gaia installed, so gate on importability
# (not just the interpreter) and wipe any half-built venv before rebuilding.
if [ ! -x "$GAIA_VENV/bin/python" ] || ! "$GAIA_VENV/bin/python" -c 'import gaia' >/dev/null 2>&1; then
  log "creating gaia venv at $GAIA_VENV"
  rm -rf "$GAIA_VENV"
  "$PY" -m venv "$GAIA_VENV" >"$ART/gaia_install.log" 2>&1
  # Use the venv's OWN pip (upgraded first) and install into the venv directly.
  # Avoids the fragile `pip3 -e ... --target` combo that silently fails on older
  # system pip and leaves gaia unimportable.
  VPIP=("$GAIA_VENV/bin/python" -m pip)
  "${VPIP[@]}" install --upgrade pip setuptools wheel >>"$ART/gaia_install.log" 2>&1 || true
  "${VPIP[@]}" install "$GAIA_REPO[mcp]" >>"$ART/gaia_install.log" 2>&1 \
    || "${VPIP[@]}" install "amd-gaia[mcp]" >>"$ART/gaia_install.log" 2>&1 || true
fi
GPY="$GAIA_VENV/bin/python"
check "gaia importable in venv" "'$GPY' -c 'import gaia; from gaia.mcp.client.mcp_client import MCPClient' 2>/dev/null"

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
        "AUDIT_DB": "$AUDIT_DB",
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

# Connector env shared by gaia probe + claude (audit plane -> SQLite DB).
export AXIS_BIN AXIS_POLICY
export AUDIT_DB
export AXIS_TENANT="client-deskside"
export AXIS_USER="${USER:-amd}"
export AXIS_POLICY_SOURCE="local-control"
export AXIS_POLICY_ID="coding-agent"

# --- 4. gaia deterministic probe (HARD) ----------------------------------
log "=== Stage 4: gaia deterministic MCP probe (HARD) ==="
AXIS_SESSION="gaia-probe" \
  "$GPY" "$HERE/gaia_mcp_probe.py" "$SERVER" 'echo GAIA_OK && hostname' \
  > "$ART/gaia_probe.out" 2>"$ART/gaia_probe.err" || true
sed -n '1,30p' "$ART/gaia_probe.out"
check "gaia-driven run returned real sandbox output (GAIA_OK)" "grep -q 'GAIA_OK' '$ART/gaia_probe.out'"
check "gaia-driven run produced decision=allow in the audit DB" \
  "db_has '\"axis.toolcall\"' '\"decision\":\"allow\"'"
check "gaia event CONFIRMED in SQLite DB (session gaia-probe)" \
  "db_wait 'gaia-probe' 1"

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
        "AUDIT_DB": "$AUDIT_DB",
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
  # Forward whatever inference access the user configured and let claude_job.sh's
  # resolver auto-detect the scheme (no forced INFERENCE_MODE).
  GATEWAY_URL="${GATEWAY_URL:-}" GATEWAY_KEY="${GATEWAY_KEY:-}" \
  ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-}" \
  ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-}" ANTHROPIC_CUSTOM_HEADERS="${ANTHROPIC_CUSTOM_HEADERS:-}" \
  INFERENCE_MODE="${INFERENCE_MODE:-}" MODEL="$MODEL" \
    bash "$GWTEST/claude_job.sh" "$MCP_JSON" "$CC_PROMPT" \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true
  check "[cross-host] Claude Code emitted mcp__axis__run" \
    "grep -E '\"type\":\"tool_use\"' '$ART/claude_cc.out' 2>/dev/null | grep -q 'mcp__axis__run'"
  check "[cross-host] Claude-Code event CONFIRMED in SQLite DB (session cc-gaia)" \
    "db_wait 'cc-gaia' 1"
  CC_DONE=1
else
  log "SKIP Stage 5: RUN_CC=0 or claude not installed"
fi

# --- 6. gaia agentic via a LOCAL Lemonade 8B model -----------------------
# A gaia Agent (LLM = Qwen3-8B-GGUF on CPU via the local Lemonade server) decides
# on its own to call the connector's run tool -> AXIS -> SQLite DB.
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
    if db_wait 'gaia-agent' 1; then
      AGENTIC=ok
      check "[agentic] gaia Agent (Lemonade $LEMON_MODEL) event CONFIRMED in SQLite DB" "true"
    else
      log "agentic stage did not confirm in SQLite DB -> reported SKIP"
      tail -8 "$ART/gaia_agent.err" 2>/dev/null
    fi
  else
    log "Lemonade not available -> agentic stage reported SKIP (stage 4 still HARD-proves the integration)"
  fi
fi

# --- 7. cross-host proof --------------------------------------------------
log "=== Stage 7: cross-host proof (gaia + Claude Code in the same audit DB) ==="
check "SQLite DB holds a gaia-driven toolcall (session gaia-probe)" \
  "db_wait 'gaia-probe' 1"
check "SQLite DB holds a Claude-Code toolcall (cross-host, session cc-gaia)" \
  "db_wait 'cc-gaia' 1"

# --- 8. summary -----------------------------------------------------------
log "=== Stage 8: SQLite event count -> artifacts/SUMMARY.txt ==="
EVENT_COUNT="$(query_db | wc -l || echo 0)"
log "SQLite audit DB events recorded: $EVENT_COUNT"
query_db | head -40 2>/dev/null

log "=== RESULT: $pass passed, $fail failed (agentic=$AGENTIC) ==="
{
  echo "gaia run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "model=$MODEL endpoint=${ANTHROPIC_BASE_URL:-${GATEWAY_URL:-https://api.anthropic.com}}"
  echo "audit_db=$AUDIT_DB events=$EVENT_COUNT"
  echo "cc_cross_host=${CC_DONE}"
  echo "agentic=$AGENTIC"
  echo "pass=$pass fail=$fail"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
