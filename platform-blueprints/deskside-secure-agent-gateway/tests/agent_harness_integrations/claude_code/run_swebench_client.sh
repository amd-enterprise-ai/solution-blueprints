#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_swebench_client.sh — solve ONE real SWE-bench instance through the
# CLIENT-SIDE governance loop and prove the audit events land in real Splunk.
#
# Inference plane:  Claude Code  ->  AMD LLM Gateway (claude-opus-4.8)
# Tool/audit plane: axis MCP connector  ->  DefenseClaw admission  ->  AXIS sandbox
#                   ->  REAL Splunk HEC (:8088, index=axis), hard-verified by reading
#                   the events back via the search API (:8089).
#
# It reuses, by relative path (NO copies of connector logic):
#   ../../../stack/axis_mcp_connector  (connector + unit tests)
#   ../../../stack/defenseclaw/run_gateway.sh
#   ../../../stack/splunk/install_splunk.sh + query_splunk.sh   (vendored)
#   ./task/{instance.json,grade.sh}   (vendored SWE-bench task definition + grader)
#
# Everything runs on one machine: the connector runs the command locally under
# AXIS and ships the audit event to Splunk directly (no orchestrator).
#
# Stages:
#   0. preconditions (node, axis, connector deps + unit tests, GATEWAY_KEY, py/git)
#   1. task workspace (clone flask @ base_commit, task venv) + AXIS swebench policy
#   2. real Splunk (reuse-or-install), HEC + mgmt health
#   3. real DefenseClaw gateway (:18970, action mode)
#   4. gateway /v1/messages preflight (claude-opus-4.8)
#   5. functional solve (HARD): Claude Code via gateway emits mcp__axis__run, edits
#      blueprints.py (persisted to host), events CONFIRMED in the Splunk index
#   6. grade (soft, reported): apply test_patch, run FAIL_TO_PASS -> SOLVED=yes/no
#   7. summary -> artifacts/SUMMARY.txt + artifacts/splunk_query.txt
#
# Env: GATEWAY_KEY (required), GATEWAY_URL, MODEL, SPLUNK_URL/SPLUNK_TGZ,
#      SPLUNK_PASS, SPLUNK_HOME, WEB_PORT/MGMT_PORT/HEC_PORT, HEC_TOKEN,
#      AXIS_BIN, DC_PORT, RUN_CC
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../../stack" && pwd)"
SPLUNK_TEST="$(cd "$CSI/splunk" && pwd)"
SWE="$(cd "$HERE/task" && pwd)"      # vendored instance.json + grade.sh
CONN="$CSI/axis_mcp_connector"
SERVER="$CONN/src/server.js"
INSTANCE="$SWE/instance.json"

# --- inference plane -----------------------------------------------------
# INFERENCE_MODE=gateway   -> AMD LLM Gateway (Ocp-Apim-Subscription-Key) [default]
# INFERENCE_MODE=anthropic -> Claude API direct (api.anthropic.com, x-api-key)
INFERENCE_MODE="${INFERENCE_MODE:-gateway}"
if [ "$INFERENCE_MODE" = "anthropic" ]; then
  GATEWAY_URL="${GATEWAY_URL:-https://api.anthropic.com}"
  GATEWAY_KEY="${ANTHROPIC_API_KEY:-}"
  MODEL="${MODEL:-claude-opus-4-8}"
else
  GATEWAY_URL="${GATEWAY_URL:-https://<llm-gateway>/Anthropic}"
  GATEWAY_KEY="${GATEWAY_KEY:-}"
  MODEL="${MODEL:-claude-opus-4.8}"
fi
export INFERENCE_MODE ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# --- control plane -------------------------------------------------------
AXIS_BIN="${AXIS_BIN:-$(command -v axis 2>/dev/null || echo /usr/local/bin/axis)}"
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

RUN_CC="${RUN_CC:-1}"
SINK="$ART/events.jsonl"
: > "$SINK"

# --- task workspace ------------------------------------------------------
WORK="$ART/workspace"
TASKVENV="${TASKVENV:-$ART/swebench-venv}"
AXIS_POLICY_FILE="$ART/axis-swebench.yaml"

export NODE_TLS_REJECT_UNAUTHORIZED=0

log(){ echo "[swe-client] $*"; }
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

# --- Splunk search helpers (read events back via REST search API) --------
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
log "=== Stage 0: preconditions ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
[ -x "$AXIS_BIN" ] || command -v "$AXIS_BIN" >/dev/null 2>&1 && log "axis: $AXIS_BIN" || log "WARN: axis not found ($AXIS_BIN)"
command -v git >/dev/null 2>&1 || { log "FATAL: git not found"; exit 2; }
command -v python3 >/dev/null 2>&1 || { log "FATAL: python3 not found"; exit 2; }

if [ ! -d "$CONN/node_modules/@modelcontextprotocol" ]; then
  log "installing connector npm deps"
  ( cd "$CONN" && npm install --no-audit --no-fund ) >"$ART/npm_install.log" 2>&1 \
    || { log "FATAL: connector npm install failed"; tail -20 "$ART/npm_install.log"; exit 2; }
fi

( cd "$CONN" && node --test ) >"$ART/unit_tests.log" 2>&1
check "connector unit tests green" "grep -q 'pass 32' '$ART/unit_tests.log' || grep -qE '# fail 0' '$ART/unit_tests.log'"
check "GATEWAY_KEY provided" "[ -n \"$GATEWAY_KEY\" ]"

# --- 1. task workspace + AXIS swebench policy ----------------------------
log "=== Stage 1: task workspace + venv + AXIS policy ==="
REPO="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['repo'])")"
BASE="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['base_commit'])")"
INSTID="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['instance_id'])")"
log "instance=$INSTID repo=$REPO base=$BASE"

if [ ! -d "$WORK/.git" ]; then
  log "cloning $REPO @ $BASE"
  rm -rf "$WORK"
  git clone "https://github.com/$REPO" "$WORK" 2>&1 | tail -2
  git -C "$WORK" checkout -q "$BASE"
else
  log "reusing checkout; resetting to $BASE"
  git -C "$WORK" reset --hard -q "$BASE" && git -C "$WORK" clean -fdq
fi

# flask 2.3 era toolchain: py3.11 + pytest 7.4.4 + werkzeug 2.3.8.
if ! "$TASKVENV/bin/python" -c 'import flask,pytest,werkzeug; assert pytest.__version__.startswith("7."); assert werkzeug.__version__.startswith("2.3.")' >/dev/null 2>&1; then
  log "creating task venv (py3.11 + flask editable + pytest 7.4.4 + werkzeug 2.3.8)"
  rm -rf "$TASKVENV"
  python3 -m venv "$TASKVENV"
  PYVER="$(python3 -c 'import sys; print(".".join(map(str,sys.version_info[:2])))')"
  SITE="$TASKVENV/lib/python$PYVER/site-packages"
  pip3 install -q -e "$WORK" "pytest==7.4.4" "werkzeug==2.3.8" --target "$SITE"
fi
check "task venv has flask+pytest7+werkzeug2.3" \
  "\"$TASKVENV/bin/python\" -c 'import flask,pytest,werkzeug; assert pytest.__version__.startswith(\"7.\"); assert werkzeug.__version__.startswith(\"2.3.\")'"

# AXIS policy: read_write on the LITERAL absolute workspace path so the model's
# edits read existing files AND persist to the host repo (landlock needs a real
# path; the shared coding-agent.yaml pins an ephemeral dir instead). read_only
# covers the uv interpreter + task venv so python3 can exec; read_write /dev for
# CPython's /dev/urandom + pytest's /dev/null.
# Halo adaptation: native (Landlock+seccomp) backend + zeroed process limits.
# The unprivileged shared Halo box has no lxc-exec/netns helper and no writable
# cgroups-v2, so a non-native provider or any non-zero requested limit makes AXIS
# fail closed. Override with AXIS_RUNTIME_PROVIDER / *_LIMIT_* if you run on a
# privileged node.
cat > "$AXIS_POLICY_FILE" <<YAML
version: 1
name: swebench-coding
runtime:
  provider: ${AXIS_RUNTIME_PROVIDER:-axis_native}
filesystem:
  read_only:
    - /usr
    - /bin
    - /lib
    - /lib64
    - /etc
    - "$HOME/.local/share/uv"
    - "$TASKVENV"
  read_write:
    - "$WORK"
    - /dev
    - "{tmpdir}"
  compatibility: best_effort
process:
  max_processes: ${AXIS_MAX_PROCESSES:-0}
  max_memory_mb: ${AXIS_MAX_MEMORY_MB:-0}
  cpu_rate_percent: ${AXIS_CPU_RATE_PERCENT:-0}
network:
  mode: block
YAML
export AXIS_POLICY="$AXIS_POLICY_FILE"

# --- 2. real Splunk Enterprise -------------------------------------------
log "=== Stage 2: real Splunk (HEC + index=$SPLUNK_INDEX) ==="
if curl -sk --fail "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 \
   && curl -sk --fail -u "$SPLUNK_USER:$SPLUNK_PASS" "$SPLUNK_MGMT_URL/services/server/info" >/dev/null 2>&1; then
  log "Splunk already up and creds valid -> reusing existing instance (skip install)"
elif [ -x "$SPLUNK_HOME/bin/splunk" ] || [ -n "${SPLUNK_URL:-}" ] || [ -n "${SPLUNK_TGZ:-}" ]; then
  SPLUNK_HOME="$SPLUNK_HOME" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
    SPLUNK_INDEX="$SPLUNK_INDEX" WEB_PORT="$WEB_PORT" MGMT_PORT="$MGMT_PORT" HEC_PORT="$HEC_PORT" \
    HEC_TOKEN="$HEC_TOKEN" SPLUNK_URL="${SPLUNK_URL:-}" SPLUNK_TGZ="${SPLUNK_TGZ:-}" \
    bash "$SPLUNK_TEST/install_splunk.sh" >"$ART/splunk_install.log" 2>&1 \
    || { log "WARN: install_splunk.sh non-zero; see splunk_install.log"; tail -25 "$ART/splunk_install.log"; }
else
  log "FATAL: Splunk not up and no SPLUNK_URL/SPLUNK_TGZ to install"; exit 2
fi

SPLUNK_UP=0
for _ in $(seq 1 60); do
  curl -sk "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 && { SPLUNK_UP=1; break; }
  sleep 1
done
check "Splunk HEC healthy on :$HEC_PORT" "[ $SPLUNK_UP -eq 1 ]"
check "Splunk mgmt/search API auth OK on :$MGMT_PORT" "curl -sk --fail -u '$SPLUNK_USER:$SPLUNK_PASS' '$SPLUNK_MGMT_URL/services/server/info' >/dev/null 2>&1"

# Splunk 10.x may ignore the requested -token on `http-event-collector create`
# and generate its own, so read the ACTUAL provisioned token back and use it for
# the connector's mcp.json (otherwise POSTs 403 and nothing gets indexed).
ACTUAL_HEC_TOKEN="$("$SPLUNK_HOME/bin/splunk" http-event-collector list \
  -uri "$SPLUNK_MGMT_URL" -auth "$SPLUNK_USER:$SPLUNK_PASS" 2>/dev/null \
  | grep -A3 'axis-orch' | grep -oE 'token=[0-9a-fA-F-]+' | head -1 | cut -d= -f2)"
if [ -n "$ACTUAL_HEC_TOKEN" ] && [ "$ACTUAL_HEC_TOKEN" != "$HEC_TOKEN" ]; then
  log "using Splunk-provisioned HEC token (differs from requested)"
  HEC_TOKEN="$ACTUAL_HEC_TOKEN"
fi

# --- 3. real DefenseClaw gateway -----------------------------------------
log "=== Stage 3: DefenseClaw gateway ==="
export DC_PORT
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-gw-swe-$$}"
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
if [ "$DC_UP" -eq 1 ]; then
  export DEFENSECLAW_HOME="$(grep -oE 'DEFENSECLAW_HOME=.*' "$DC_OUT" | tail -1 | cut -d= -f2-)"
else
  log "WARN: DefenseClaw gateway failed to start; see $DC_OUT"
fi
check "DefenseClaw gateway healthy on :$DC_PORT" "[ ${DC_UP:-0} -eq 1 ]"

# --- 4. gateway preflight -------------------------------------------------
log "=== Stage 4: gateway /v1/messages preflight ($MODEL) ==="
check "GATEWAY_KEY provided" "[ -n \"$GATEWAY_KEY\" ]"
if [ "$INFERENCE_MODE" = "anthropic" ]; then
  AUTH_HEADER="x-api-key: $GATEWAY_KEY"
else
  AUTH_HEADER="Ocp-Apim-Subscription-Key: $GATEWAY_KEY"
fi
curl -sS -m 60 "$GATEWAY_URL/v1/messages" \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -H "$AUTH_HEADER" \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly: GATEWAY_OK\"}]}" \
  > "$ART/gateway_messages_probe.json" 2>"$ART/gateway_messages_probe.err"
check "gateway returns a real completion ($MODEL)" \
  "grep -q '\"type\":\"message\"' '$ART/gateway_messages_probe.json' && grep -q '\"text\"' '$ART/gateway_messages_probe.json'"

# --- 5. functional SWE-bench solve (HARD) --------------------------------
SESSION="cc-swe-func"
if [ "${RUN_CC:-1}" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  log "=== Stage 5: functional Claude Code solve via gateway ($MODEL) ==="
  MCP_JSON="$ART/.mcp.json"
  sed -e "s#@SERVER@#$SERVER#g" \
      -e "s#@AXIS_BIN@#$AXIS_BIN#g" \
      -e "s#@AXIS_POLICY@#$AXIS_POLICY_FILE#g" \
      -e "s#@DC_PORT@#$DC_PORT#g" \
      -e "s#@DC_TOKEN@#$DEFENSECLAW_GATEWAY_TOKEN#g" \
      -e "s#@SINK@#$SINK#g" \
      -e "s#@HEC_URL@#$SPLUNK_HEC_URL#g" \
      -e "s#@HEC_TOKEN@#$HEC_TOKEN#g" \
      -e "s#@SESSION@#$SESSION#g" \
      "$HERE/mcp.json.tmpl" > "$MCP_JSON"

  GATEWAY_URL="$GATEWAY_URL" GATEWAY_KEY="$GATEWAY_KEY" MODEL="$MODEL" \
    INFERENCE_MODE="$INFERENCE_MODE" ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
    WORKDIR="$WORK" TASKVENV="$TASKVENV" \
    bash "$HERE/claude_job.sh" "$MCP_JSON" "$HERE/prompt.txt" \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true

  check "[functional] Claude Code got a real gateway response" \
    "grep '\"type\":\"result\"' '$ART/claude_cc.out' 2>/dev/null | grep -q '\"is_error\":false'"
  check "[functional] model emitted mcp__axis__run" \
    "grep -E '\"type\":\"tool_use\"' '$ART/claude_cc.out' 2>/dev/null | grep -q 'mcp__axis__run'"
  check "[functional] edit persisted to host repo (blueprints.py)" \
    "grep -q \"may not be empty\" '$WORK/src/flask/blueprints.py' 2>/dev/null"
  check "[functional] toolcall event(s) CONFIRMED in real Splunk index" \
    "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=$SESSION event=axis.toolcall decision=allow' 1"
  check "[functional] session_start CONFIRMED in real Splunk index" \
    "splunk_wait 'search index=$SPLUNK_INDEX | spath | search identity.session=$SESSION event=axis.session_start' 1"
else
  log "SKIP Stage 5: RUN_CC=0 or claude not installed"
fi

# --- 6. grade (soft, reported) -------------------------------------------
log "=== Stage 6: grade (soft / reported) ==="
SOLVED="unknown"
if [ -d "$WORK/.git" ]; then
  bash "$SWE/grade.sh" "$WORK" "$INSTANCE" "$TASKVENV/bin/python" "$ART" > "$ART/grade.out" 2>&1 || true
  grep -q '^SOLVED=yes' "$ART/grade.out" && SOLVED="yes" || { grep -q '^SOLVED=no' "$ART/grade.out" && SOLVED="no"; }
  log "grade: SOLVED=$SOLVED"
  tail -5 "$ART/grade.out" 2>/dev/null
fi

# --- 7. summary -----------------------------------------------------------
log "=== Dumping the Splunk index (search API) -> artifacts/splunk_query.txt ==="
SPLUNK_MGMT_URL="$SPLUNK_MGMT_URL" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
  SPLUNK_INDEX="$SPLUNK_INDEX" EARLIEST="-1h" \
  bash "$SPLUNK_TEST/query_splunk.sh" > "$ART/splunk_query.txt" 2>&1 || true
sed -n '1,40p' "$ART/splunk_query.txt" 2>/dev/null

log "=== RESULT: $pass passed, $fail failed (SOLVED=$SOLVED) ==="
{
  echo "swebench run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "instance=$INSTID model=$MODEL gateway=$GATEWAY_URL"
  echo "splunk_up=${SPLUNK_UP:-0} defenseclaw_up=${DC_UP:-0}"
  echo "solved=$SOLVED"
  echo "pass=$pass fail=$fail"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
