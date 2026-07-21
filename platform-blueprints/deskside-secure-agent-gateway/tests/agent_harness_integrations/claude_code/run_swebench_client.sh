#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_swebench_client.sh — solve ONE real SWE-bench instance through the
# AMD-only client-side governance loop (no DefenseClaw, no Splunk).
#
# Inference plane:  Claude Code  ->  Anthropic-compatible gateway / Anthropic API
# Tool/audit plane: axis MCP connector  ->  AXIS sandbox (sole enforcement)
#                   ->  SQLite audit DB (local file)
#
# Reuses by relative path (no copies of connector logic):
#   ../../../stack/axis_mcp_connector  (connector + unit tests)
#   ./task/{instance.json,grade.sh}   (vendored SWE-bench task)
#
# Stages:
#   0. preconditions (node, axis, connector deps + unit tests, inference access, py/git)
#   1. task workspace (clone flask @ base_commit, task venv) + AXIS swebench policy
#   2. inference preflight — real model response
#   3. functional solve: Claude Code emits mcp__axis__run, edits blueprints.py,
#      events confirmed in the SQLite audit DB
#   4. grade (soft, reported): apply test_patch, run FAIL_TO_PASS -> SOLVED=yes/no
#   5. summary -> artifacts/SUMMARY.txt
#
# Inference access (bring your own; see tests/lib/inference_env.sh): set one of
#   ANTHROPIC_API_KEY | ANTHROPIC_BASE_URL+ANTHROPIC_AUTH_TOKEN |
#   ANTHROPIC_BASE_URL+ANTHROPIC_CUSTOM_HEADERS. Custom-header alias: GATEWAY_KEY.
# Env: MODEL, AXIS_BIN, AUDIT_DB, RUN_CC, MAXTURNS, CC_TIMEOUT
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../../stack" && pwd)"
SWE="$(cd "$HERE/task" && pwd)"
CONN="$CSI/axis_mcp_connector"
SERVER="$CONN/src/server.js"
INSTANCE="$SWE/instance.json"

# --- inference plane ---------------------------------------------------------
# Bring your own Anthropic-compatible access — Anthropic direct, or any gateway
# via a bearer/x-api-key token or a custom header. No endpoint is assumed; the
# resolver exits with a how-to if nothing is configured. See
# tests/lib/inference_env.sh (custom-header alias: set GATEWAY_KEY).
# shellcheck source=../../lib/inference_env.sh
source "$HERE/../../lib/inference_env.sh"
resolve_inference_access || exit 2
GATEWAY_URL="$INFER_BASE_URL"
MODEL="${MODEL:-$INFER_MODEL_DEFAULT}"

# --- control + audit plane ---------------------------------------------------
AXIS_BIN="${AXIS_BIN:-$(command -v axis 2>/dev/null || echo axis)}"
AUDIT_DB="${AUDIT_DB:-$ART/audit.db}"
# shellcheck source=../../lib/audit_db.sh
source "$HERE/../../lib/audit_db.sh"
RUN_CC="${RUN_CC:-1}"
WORK="$ART/workspace"
TASKVENV="${TASKVENV:-$ART/swebench-venv}"
AXIS_POLICY_FILE="$ART/axis-swebench.yaml"
SESSION="cc-swe-func"
MAXTURNS="${MAXTURNS:-40}"
CC_TIMEOUT="${CC_TIMEOUT:-1200}"

log(){ echo "[swe-client] $*"; }
pass=0; fail=0
check(){ if eval "$2"; then log "PASS: $1"; pass=$((pass+1)); else log "FAIL: $1"; fail=$((fail+1)); fi; }

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
NODE_BIN_DIR="$(dirname "$(ls -t "$NVM_DIR"/versions/node/*/bin/node 2>/dev/null | head -1)" 2>/dev/null)"
export PATH="$HOME/.local/bin:${NODE_BIN_DIR:-}:$PATH"

# --- 0. preconditions --------------------------------------------------------
log "=== Stage 0: preconditions ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
command -v "$AXIS_BIN" >/dev/null 2>&1 && log "axis: $(command -v "$AXIS_BIN")" \
  || { log "FATAL: axis binary not found ($AXIS_BIN) — run platforms/halo/setup.sh first"; exit 2; }
command -v git >/dev/null 2>&1   || { log "FATAL: git not found"; exit 2; }
command -v python3 >/dev/null 2>&1 || { log "FATAL: python3 not found"; exit 2; }

if [ ! -d "$CONN/node_modules/@modelcontextprotocol" ]; then
  log "installing connector npm deps"
  ( cd "$CONN" && npm install --no-audit --no-fund ) >"$ART/npm_install.log" 2>&1 \
    || { log "FATAL: connector npm install failed"; exit 2; }
fi
( cd "$CONN" && node --test ) >"$ART/unit_tests.log" 2>&1
check "connector unit tests green" "grep -qE '# fail 0' '$ART/unit_tests.log'"
check "inference access configured" "[ -n \"${INFER_AUTH_HEADER:-}\" ]"

# --- 1. task workspace + AXIS swebench policy --------------------------------
log "=== Stage 1: task workspace + venv + AXIS policy ==="
REPO="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['repo'])")"
BASE="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['base_commit'])")"
INSTID="$(python3 -c "import json;print(json.load(open('$INSTANCE'))['instance_id'])")"
log "instance=$INSTID  repo=$REPO  base=$BASE"

if [ ! -d "$WORK/.git" ]; then
  log "cloning $REPO @ $BASE"
  rm -rf "$WORK"
  git clone "https://github.com/$REPO" "$WORK" 2>&1 | tail -2
  git -C "$WORK" checkout -q "$BASE"
else
  log "reusing checkout; resetting to $BASE"
  git -C "$WORK" reset --hard -q "$BASE" && git -C "$WORK" clean -fdq
fi

# We can build the preferred py3.11 grade venv iff python3.11 or uv is present.
# When we can, also rebuild a stale non-3.11 venv: a reused py3.12 venv would
# false-fail the grade even though the deps are present.
NEED_PY="3.11"; { command -v python3.11 || command -v uv; } >/dev/null 2>&1 || NEED_PY=""
if ! "$TASKVENV/bin/python" -c "
import sys
try:
    import flask, pytest, werkzeug
except Exception:
    sys.exit(1)
if not (pytest.__version__.startswith('7.') and werkzeug.__version__.startswith('2.3.')):
    sys.exit(1)
need = '$NEED_PY'
if need and '.'.join(map(str, sys.version_info[:2])) != need:
    sys.exit(1)
" >/dev/null 2>&1; then
  log "creating task venv (py3.11 + flask editable + pytest 7.4.4 + werkzeug 2.3.8)"
  rm -rf "$TASKVENV"
  # pallets__flask-5014 is a py3.11-era instance. On py3.12 flask promotes the
  # pkgutil.get_loader DeprecationWarning to an error, which false-fails the
  # FAIL_TO_PASS grade. Build the grade venv on 3.11: prefer python3.11, else let
  # uv fetch a 3.11, else fall back to whatever python3 is (grade may false-negative).
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv "$TASKVENV"
  elif command -v uv >/dev/null 2>&1; then
    # --seed installs pip into the venv so we can use its own interpreter below.
    uv venv --seed --python 3.11 "$TASKVENV" >/dev/null
  else
    log "WARN: no python3.11 or uv found; using $(python3 --version 2>&1) — the soft SWE-bench grade may false-negative on py3.12+"
    python3 -m venv "$TASKVENV"
  fi
  # Install with the venv's own interpreter (not the host pip3 + --target), so the
  # deps land in this venv regardless of the host's pip version/availability.
  "$TASKVENV/bin/python" -m pip install -q -e "$WORK" "pytest==7.4.4" "werkzeug==2.3.8"
fi
check "task venv has flask+pytest7+werkzeug2.3" \
  "\"$TASKVENV/bin/python\" -c 'import flask,pytest,werkzeug; assert pytest.__version__.startswith(\"7.\"); assert werkzeug.__version__.startswith(\"2.3.\")'"

# AXIS swebench policy: grants read_write on the literal workspace so edits
# persist to the host repo. Network blocked — the model must not exfiltrate code.
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
rm -f "$AUDIT_DB"

# --- 2. inference preflight --------------------------------------------------
log "=== Stage 2: inference /v1/messages preflight ($MODEL) ==="
curl -sS -m 60 "$INFER_BASE_URL/v1/messages" \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -H "$INFER_AUTH_HEADER" \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly: GATEWAY_OK\"}]}" \
  > "$ART/gateway_messages_probe.json" 2>"$ART/gateway_messages_probe.err"
check "endpoint returns a real completion ($MODEL)" \
  "grep -q '\"type\":\"message\"' '$ART/gateway_messages_probe.json' && grep -q '\"text\"' '$ART/gateway_messages_probe.json'"

# --- 3. functional SWE-bench solve -------------------------------------------
if [ "${RUN_CC:-1}" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  log "=== Stage 3: functional Claude Code solve via endpoint ($MODEL) ==="
  MCP_JSON="$ART/.mcp.json"
  # Strip the leading '#' license header before substituting — the rendered file
  # is parsed as strict JSON, which has no comment syntax.
  sed -e '/^#/d' \
      -e "s#@SERVER@#$SERVER#g" \
      -e "s#@AXIS_BIN@#$AXIS_BIN#g" \
      -e "s#@AXIS_POLICY@#$AXIS_POLICY_FILE#g" \
      -e "s#@AUDIT_DB@#$AUDIT_DB#g" \
      -e "s#@SESSION@#$SESSION#g" \
      -e "s#@AXIS_USER@#${USER:-amd}#g" \
      "$HERE/mcp.json.tmpl" > "$MCP_JSON"

  # Auth flows through the exported ANTHROPIC_* env resolved above; pass only the
  # per-run knobs. INFERENCE_MODE (optional override) and GATEWAY_KEY inherit.
  MODEL="$MODEL" WORKDIR="$WORK" TASKVENV="$TASKVENV" \
    bash "$HERE/claude_job.sh" "$MCP_JSON" "$HERE/prompt.txt" \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true

  check "[functional] Claude Code got a real endpoint response" \
    "grep '\"type\":\"result\"' '$ART/claude_cc.out' 2>/dev/null | grep -q '\"is_error\":false'"
  check "[functional] model emitted mcp__axis__run" \
    "grep -E '\"type\":\"tool_use\"' '$ART/claude_cc.out' 2>/dev/null | grep -q 'mcp__axis__run'"
  check "[functional] edit persisted to host repo (blueprints.py)" \
    "grep -q 'may not be empty' '$WORK/src/flask/blueprints.py' 2>/dev/null"
  check "[functional] axis.toolcall(allow) confirmed in SQLite audit DB" \
    "db_has '\"axis.toolcall\"' '\"decision\":\"allow\"'"
  check "[functional] session_start confirmed in SQLite audit DB" \
    "db_has '\"axis.session_start\"'"

  # Show the audit DB summary
  log "=== SQLite audit events (session=$SESSION) ==="
  query_db | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        print(f\"  {e.get('event','?'):30s} seq={e.get('command',{}).get('seq','') if 'command' in e else ''} decision={e.get('decision','')}\")
    except Exception:
        pass
" 2>/dev/null || true

else
  log "SKIP Stage 3: RUN_CC=0 or claude not installed"
fi

# --- 4. grade (soft, reported) -----------------------------------------------
log "=== Stage 4: grade (soft / reported) ==="
SOLVED="unknown"
if [ -d "$WORK/.git" ]; then
  bash "$SWE/grade.sh" "$WORK" "$INSTANCE" "$TASKVENV/bin/python" "$ART" > "$ART/grade.out" 2>&1 || true
  grep -q '^SOLVED=yes' "$ART/grade.out" && SOLVED="yes" || { grep -q '^SOLVED=no' "$ART/grade.out" && SOLVED="no"; }
  log "grade: SOLVED=$SOLVED"
  tail -5 "$ART/grade.out" 2>/dev/null
fi

# --- 5. summary ---------------------------------------------------------------
log "=== RESULT: $pass passed, $fail failed (SOLVED=$SOLVED) ==="
{
  echo "swebench run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "instance=$INSTID  model=$MODEL  endpoint=$GATEWAY_URL"
  echo "audit_db=$AUDIT_DB"
  echo "solved=$SOLVED"
  echo "pass=$pass  fail=$fail"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
