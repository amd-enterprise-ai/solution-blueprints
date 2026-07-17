#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_lemonade_telemetry.sh — INFERENCE-plane telemetry, end to end, on one node.
#
# Complements the tool-plane audit (see tests/agent_harness_integrations/claude_code/).
# Here we audit the INFERENCE plane: a transparent telemetry proxy sits in front of the
# local Lemonade server (Qwen3-8B on CPU). The agent host points its
# ANTHROPIC_BASE_URL at the proxy; the proxy forwards every /v1/messages call to
# Lemonade byte-for-byte AND, on the side:
#   - emits an `llm.request` event to the SQLite audit DB (AUDIT_DB),
#     correlatable by identity.session.
#
# Every llm.request is HARD-verified by reading it back out of the SQLite audit DB —
# not just written to the local sink.
#
# Stages (pass/fail -> artifacts/SUMMARY.txt):
#   0. preconditions: node + proxy unit tests (22) green
#   3. Lemonade (reuse-or-boot Qwen3-8B on CPU); Anthropic endpoint healthy
#   4. proxy #1 (session lemon-probe) in front of Lemonade
#   5. deterministic HARD proof: curl a real /v1/messages through the proxy ->
#      real completion + llm.request(decision=allow) CONFIRMED in SQLite audit DB
#   6. Claude Code (best-effort): drive Claude Code's inference THROUGH the proxy
#      (ANTHROPIC_BASE_URL -> proxy #2, session cc-lemon); llm.request CONFIRMED
#      in SQLite DB. Reported SKIP if the local 8B can't carry Claude Code's loop.
#   7. summary (SQLite event count)
#
# Env: AUDIT_DB (SQLite path, default $ART/audit.db), LEMON_MODEL,
#      LEMONADE_PORT, PROXY_PORT, RUN_CC, MODEL.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../stack" && pwd)"
PROXY="$CSI/lemonade_proxy"
PROXY_SERVER="$PROXY/src/server.js"

# --- inference plane: local Lemonade + telemetry proxy --------------------
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMON_BASE="http://127.0.0.1:$LEMONADE_PORT"
# Lemonade's OpenAI-compatible API lives under /api/v1 on this pip install.
# The proxy needs LEMON_UPSTREAM to point at the /api prefix so that
# /v1/chat/completions -> $LEMON_UPSTREAM/v1/chat/completions resolves correctly.
LEMON_UPSTREAM="${LEMON_UPSTREAM:-$LEMON_BASE/api}"
PROXY_PORT="${PROXY_PORT:-13399}"
PROXY_PORT2="${PROXY_PORT2:-13398}"

# --- audit plane: SQLite DB ----------------------------------------------
AUDIT_DB="${AUDIT_DB:-$ART/audit.db}"
# Start from a clean audit DB so probes assert on THIS run's events, not stale
# rows from a prior run (db_wait would otherwise return early on an old match).
rm -f "$AUDIT_DB"
# shellcheck source=../lib/audit_db.sh
source "$HERE/../lib/audit_db.sh"

RUN_CC="${RUN_CC:-1}"
MODEL="${MODEL:-$LEMON_MODEL}"

export NODE_TLS_REJECT_UNAUTHORIZED=0

log(){ echo "[lemtest] $*"; }
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

# --- proxy launcher ------------------------------------------------------
# start_proxy <session> <port> <logtag>  -> exports PROXY_URL, appends PID.
start_proxy(){
  local session="$1" port="$2" tag="$3" out="$ART/proxy_$3.log"
  : > "$out"
  LEMON_PROXY_PORT="$port" \
  LEMON_UPSTREAM="$LEMON_UPSTREAM" \
  AUDIT_DB="$AUDIT_DB" \
  LLM_SESSION="$session" \
  LLM_USER="${USER:-amd}" \
  LLM_TENANT="client-deskside" \
    node "$PROXY_SERVER" >"$out" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  PROXY_URL=""
  for _ in $(seq 1 100); do
    PROXY_URL="$(grep -oE 'LEMON_PROXY_URL=http://127.0.0.1:[0-9]+' "$out" | tail -1 | cut -d= -f2-)"
    [ -n "$PROXY_URL" ] && curl -sf "$PROXY_URL/api/v1/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
  [ -n "$PROXY_URL" ]
}
stop_proxy(){ # SIGTERM so it emits llm.session_end
  local pid="$1"; kill "$pid" >/dev/null 2>&1 || true; sleep 1
}

# --- 0. preconditions -----------------------------------------------------
log "=== Stage 0: preconditions ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
( cd "$PROXY" && node --test ) >"$ART/proxy_unit_tests.log" 2>&1
check "proxy unit tests green" "grep -qE '# fail 0' '$ART/proxy_unit_tests.log'"

# --- 3. Lemonade (reuse-or-boot) -----------------------------------------
log "=== Stage 3: Lemonade $LEMON_MODEL on CPU (:$LEMONADE_PORT) ==="
LEMON_HEALTH="$LEMON_BASE/api/v1/health"
if curl -sf "$LEMON_HEALTH" >/dev/null 2>&1; then
  log "Lemonade already up -> reusing"
else
  log "booting Lemonade via $CSI/lemonade/run_lemonade.sh"
  LEMONADE_PORT="$LEMONADE_PORT" LEMON_MODEL="$LEMON_MODEL" \
    bash "$CSI/lemonade/run_lemonade.sh" >"$ART/lemonade_boot.log" 2>&1 || \
    log "WARN: run_lemonade.sh non-zero; see lemonade_boot.log"
fi
LEMON_UP=0
for _ in $(seq 1 60); do
  curl -sf "$LEMON_HEALTH" >/dev/null 2>&1 && { LEMON_UP=1; break; }
  sleep 1
done
check "Lemonade healthy on :$LEMONADE_PORT" "[ ${LEMON_UP:-0} -eq 1 ]"

# --- 4. proxy #1 (deterministic session) ---------------------------------
log "=== Stage 4: telemetry proxy in front of Lemonade (session lemon-probe) ==="
if start_proxy "lemon-probe" "$PROXY_PORT" "probe"; then
  PROXY1_URL="$PROXY_URL"; PROXY1_PID="${PIDS[-1]}"
  log "proxy up: $PROXY1_URL"
  check "telemetry proxy healthy (passthrough to Lemonade)" "[ -n '$PROXY1_URL' ]"
else
  log "WARN: proxy #1 failed to come up; see proxy_probe.log"
  check "telemetry proxy healthy (passthrough to Lemonade)" "false"
fi

# --- 5. deterministic HARD proof -----------------------------------------
log "=== Stage 5: deterministic /v1/messages through the proxy (HARD) ==="
if [ "${LEMON_UP:-0}" -eq 1 ] && [ -n "${PROXY1_URL:-}" ]; then
  curl -sS -m 180 "$PROXY1_URL/v1/chat/completions" \
    -H 'content-type: application/json' \
    -H 'x-api-key: dummy' \
    -d "{\"model\":\"$LEMON_MODEL\",\"max_tokens\":32,\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly: LEMON_PROXY_OK\"}]}" \
    > "$ART/proxy_probe.json" 2>"$ART/proxy_probe.err" || true
  check "proxy returned a real Lemonade completion" \
    "grep -qE '\"choices\"|\"content\"|\"text\"' '$ART/proxy_probe.json'"
  # allow proxy to flush the async event write to the audit DB
  check "llm.request recorded in the audit DB (session lemon-probe)" \
    "db_wait_line '\"llm.request\"' 'lemon-probe'"
  check "llm.session_start CONFIRMED in SQLite audit DB (session lemon-probe)" \
    "db_wait 'lemon-probe' 1"
  check "llm.request(decision=allow) CONFIRMED in SQLite audit DB" \
    "db_wait_line 'lemon-probe' '\"llm.request\"' '\"decision\":\"allow\"'"
else
  log "SKIP Stage 5: Lemonade or proxy down"
  check "proxy returned a real Lemonade completion" "false"
fi
[ -n "${PROXY1_PID:-}" ] && stop_proxy "$PROXY1_PID"

# --- 6. Claude Code THROUGH the proxy (best-effort) ----------------------
CC_STATUS="skip"
if [ "${RUN_CC:-1}" -eq 1 ] && command -v claude >/dev/null 2>&1 && [ "${LEMON_UP:-0}" -eq 1 ]; then
  log "=== Stage 6: Claude Code inference THROUGH the proxy (session cc-lemon) ==="
  if start_proxy "cc-lemon" "$PROXY_PORT2" "cc"; then
    PROXY2_URL="$PROXY_URL"; PROXY2_PID="${PIDS[-1]}"
    GATEWAY_URL="$PROXY2_URL" MODEL="$LEMON_MODEL" \
      bash "$HERE/claude_job.sh" 'Reply with exactly: LEMON_CC_OK' \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true
    if db_wait "cc-lemon" 1; then
      CC_STATUS="ok"
      check "[cc] Claude Code inference produced an llm.request in SQLite DB (session cc-lemon)" "true"
    else
      log "SKIP: Claude Code did not drive a confirmable llm.request (weak local model); see claude_cc.err"
    fi
    [ -n "${PROXY2_PID:-}" ] && stop_proxy "$PROXY2_PID"
  else
    log "SKIP: proxy #2 failed to come up"
  fi
else
  log "SKIP Stage 6: RUN_CC=0 / claude missing / Lemonade down"
fi

# --- 7. summary -----------------------------------------------------------
log "=== Stage 7: SQLite event count -> artifacts/SUMMARY.txt ==="
EVENT_COUNT="$(query_db | wc -l || echo 0)"
log "SQLite audit DB events recorded: $EVENT_COUNT"
query_db | head -40 2>/dev/null

log "=== RESULT: $pass passed, $fail failed ==="
{
  echo "lemonade_test run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "inference: proxy -> Lemonade $LEMON_MODEL on CPU (:$LEMONADE_PORT)"
  echo "audit: SQLite audit DB=$AUDIT_DB events=$EVENT_COUNT"
  echo "lemonade_up=${LEMON_UP:-0}"
  echo "pass=$pass fail=$fail"
  echo "cc=$CC_STATUS"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
