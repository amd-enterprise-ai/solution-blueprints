#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_router_telemetry.sh — CLIENT-SIDE semantic-router A/B, end to end, one node.
#
# Sibling of ../lemonade_test/run_lemonade_telemetry.sh. That test
# proved the inference-plane telemetry proxy (transparent, DefenseClaw guardrails,
# llm.request -> real Splunk index=axis). This test adds the vLLM Semantic Router
# to that proxy: per prompt the proxy CONSULTS the router's standalone classify
# API (POST /api/v1/classify/intent — NO Envoy, NO inference) and, on a "hard"
# verdict AND a configured frontier key, escalates the request to the frontier
# tier (AMD LLM Gateway, Anthropic-compatible); otherwise it stays byte-for-byte
# on local Lemonade. The routing decision is surfaced on the client response as
# additive x-lemon-* headers AND recorded in a new `routing` block on every
# llm.request Splunk event.
#
# Toggle is a PROXY env (LEMON_ROUTER=on|off). The runner starts a BASELINE proxy
# (router off) and a ROUTER-ON proxy and runs the A/B against both.
#
# Every llm.request is HARD-verified by reading it back out of Splunk's search
# API — routing block included.
#
# Stages (pass/fail -> artifacts/SUMMARY.txt):
#   0. preconditions: node + proxy unit tests (37) green
#   1. real Splunk (reuse-or-install); HEC + mgmt/search health
#   2. DefenseClaw gateway (:18970)
#   3. Lemonade (reuse-or-boot Qwen3-8B on CPU, :13305) — the local tier
#   4. semantic-router classify API (reuse a local ~/repos/semantic-router build)
#   5. frontier preflight (AMD LLM Gateway) — real completion if a key is set
#   6. BASELINE (router off, session router-baseline): all local, confirmed in Splunk
#   7. ROUTER-ON (router on, session router-on): easy->local, hard->frontier
#      decision; routing correctness; routing block CONFIRMED in index=axis
#   8. Claude Code THROUGH the router-on proxy (best-effort, session cc-router)
#   9. summary + splunk_query.txt
#
# Env: SPLUNK_PASS, HEC_TOKEN (reuse the node's shared Splunk), GATEWAY_KEY (or
#      ANTHROPIC_API_KEY / FRONTIER_AUTH_KEY) for the frontier tier, LEMON_MODEL,
#      LEMONADE_PORT, ROUTER_API_PORT, DC_PORT, RUN_CC, FRONTIER_* overrides.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/artifacts"; mkdir -p "$ART"
CSI="$(cd "$HERE/../../stack" && pwd)"
SPLUNK_TEST="$(cd "$CSI/splunk" && pwd)"          # vendored real-Splunk install + query
PROXY="$CSI/lemonade_proxy"
PROXY_SERVER="$PROXY/src/server.js"

# --- inference plane: local Lemonade (local tier) ------------------------
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMON_BASE="http://127.0.0.1:$LEMONADE_PORT"
# Lemonade's OpenAI-compatible API lives under /api/v1 on this pip install.
LEMON_UPSTREAM="${LEMON_UPSTREAM:-$LEMON_BASE/api}"
PROXY_BASELINE_PORT="${PROXY_BASELINE_PORT:-13399}"
PROXY_ROUTER_PORT="${PROXY_ROUTER_PORT:-13398}"
PROXY_CC_PORT="${PROXY_CC_PORT:-13397}"

# --- semantic router (classify API only) ---------------------------------
# NOTE: :8088 is Splunk HEC here, so the classify API runs on a distinct port.
ROUTER_REPO_DIR="${ROUTER_REPO_DIR:-$HOME/repos/semantic-router}"
ROUTER_API_PORT="${ROUTER_API_PORT:-18088}"
ROUTER_URL="http://127.0.0.1:$ROUTER_API_PORT"
# The router binary always starts a gRPC ExtProc server (default :50051) and a
# Prometheus metrics server (default :9190) even though the client-side proxy
# only consults the classify API. Use non-default ports so a pre-existing router
# on the machine (e.g. one holding :50051) doesn't cause a fatal bind clash.
ROUTER_EXTPROC_PORT="${ROUTER_EXTPROC_PORT:-50151}"
ROUTER_METRICS_PORT="${ROUTER_METRICS_PORT:-19190}"

# --- frontier tier (default AMD LLM Gateway; Anthropic-compatible) -------
FRONTIER_UPSTREAM="${FRONTIER_UPSTREAM:-https://<llm-gateway>/Anthropic}"
FRONTIER_MODEL="${FRONTIER_MODEL:-claude-opus-4-8}"
FRONTIER_AUTH_HEADER="${FRONTIER_AUTH_HEADER:-Ocp-Apim-Subscription-Key}"
FRONTIER_AUTH_KEY="${FRONTIER_AUTH_KEY:-${GATEWAY_KEY:-${ANTHROPIC_API_KEY:-}}}"
FRONTIER_EXTRA_HEADERS="${FRONTIER_EXTRA_HEADERS:-}"

# --- control plane -------------------------------------------------------
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
SINK="$ART/events.jsonl"; : > "$SINK"

# Node's fetch (proxy HEC POST) and curl talk to Splunk's self-signed HEC.
export NODE_TLS_REJECT_UNAUTHORIZED=0

log(){ echo "[rtrtest] $*"; }
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

# --- Splunk search helpers -----------------------------------------------
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

# --- proxy launcher ------------------------------------------------------
# start_proxy <session> <port> <logtag> <router:on|off> -> exports PROXY_URL.
start_proxy(){
  local session="$1" port="$2" tag="$3" router="$4" out="$ART/proxy_$3.log"
  : > "$out"
  LEMON_PROXY_PORT="$port" \
  LEMON_UPSTREAM="$LEMON_UPSTREAM" \
  DEFENSECLAW_URL="http://127.0.0.1:$DC_PORT" \
  DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-}" \
  DEFENSECLAW_INFERENCE_MODE="observe" \
  SPLUNK_SINK="$SINK" \
  SPLUNK_HEC_URL="$SPLUNK_HEC_URL" \
  SPLUNK_HEC_TOKEN="$HEC_TOKEN" \
  LEMON_ROUTER="$router" \
  SEMANTIC_ROUTER_URL="$ROUTER_URL" \
  FRONTIER_UPSTREAM="$FRONTIER_UPSTREAM" \
  FRONTIER_MODEL="$FRONTIER_MODEL" \
  FRONTIER_AUTH_HEADER="$FRONTIER_AUTH_HEADER" \
  FRONTIER_AUTH_KEY="$FRONTIER_AUTH_KEY" \
  FRONTIER_EXTRA_HEADERS="$FRONTIER_EXTRA_HEADERS" \
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
stop_proxy(){ local pid="$1"; kill "$pid" >/dev/null 2>&1 || true; sleep 1; }

# --- router classify readiness -------------------------------------------
# The classify API is ready once a POST /api/v1/classify/intent returns 200 (the
# candle embedding model has loaded). GET /health is tried first if present.
router_wait(){
  local code
  for _ in $(seq 1 90); do
    curl -sf "$ROUTER_URL/health" >/dev/null 2>&1 && return 0
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST \
      "$ROUTER_URL/api/v1/classify/intent" -H 'content-type: application/json' \
      -d '{"text":"ping"}' 2>/dev/null)"
    [ "$code" = "200" ] && return 0
    sleep 2
  done
  return 1
}

# --- 0. preconditions -----------------------------------------------------
log "=== Stage 0: preconditions ==="
command -v node >/dev/null 2>&1 || { log "FATAL: node not found"; exit 2; }
log "node: $(node --version)"
( cd "$PROXY" && env -u FRONTIER_AUTH_KEY -u FRONTIER_AUTH_HEADER -u FRONTIER_UPSTREAM -u FRONTIER_EXTRA_HEADERS node --test ) >"$ART/proxy_unit_tests.log" 2>&1
check "proxy unit tests green" "grep -qE '# fail 0' '$ART/proxy_unit_tests.log'"
# The probe's pure-logic unit tests need pytest. It's a pre-flight only (the HARD
# proof is the Splunk stages), so if pytest is absent on this node we SKIP the
# check rather than fail the whole run.
if python3 -c 'import pytest' >/dev/null 2>&1; then
  ( cd "$HERE" && python3 -m pytest test_router_ab_probe.py -q ) >"$ART/probe_unit_tests.log" 2>&1
  check "A/B probe unit tests green" "grep -qE '[0-9]+ passed' '$ART/probe_unit_tests.log'"
else
  log "SKIP: pytest not installed -> probe unit tests (verified off-node); pip install --user pytest to enable"
  echo "pytest not installed on this node" > "$ART/probe_unit_tests.log"
fi

# --- 1. real Splunk -------------------------------------------------------
log "=== Stage 1: real Splunk (HEC + index=$SPLUNK_INDEX) ==="
if [ ! -x "$SPLUNK_HOME/bin/splunk" ] && [ -z "${SPLUNK_URL:-}" ] && [ -z "${SPLUNK_TGZ:-}" ]; then
  log "FATAL: Splunk not installed at $SPLUNK_HOME and no SPLUNK_URL/SPLUNK_TGZ given"; exit 2
fi
if curl -sk --fail "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 \
   && curl -sk --fail -u "$SPLUNK_USER:$SPLUNK_PASS" "$SPLUNK_MGMT_URL/services/server/info" >/dev/null 2>&1; then
  log "Splunk already up and creds valid -> reusing existing instance (skip install)"
else
  SPLUNK_HOME="$SPLUNK_HOME" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
    SPLUNK_INDEX="$SPLUNK_INDEX" WEB_PORT="$WEB_PORT" MGMT_PORT="$MGMT_PORT" HEC_PORT="$HEC_PORT" \
    HEC_TOKEN="$HEC_TOKEN" SPLUNK_URL="${SPLUNK_URL:-}" SPLUNK_TGZ="${SPLUNK_TGZ:-}" \
    bash "$SPLUNK_TEST/install_splunk.sh" >"$ART/splunk_install.log" 2>&1 \
    || { log "WARN: install_splunk.sh non-zero; see log"; tail -25 "$ART/splunk_install.log"; }
fi
SPLUNK_UP=0
for _ in $(seq 1 60); do
  curl -sk "$SPLUNK_HEC_URL/services/collector/health" >/dev/null 2>&1 && { SPLUNK_UP=1; break; }
  sleep 1
done
check "Splunk HEC healthy on :$HEC_PORT" "[ $SPLUNK_UP -eq 1 ]"
check "Splunk mgmt/search API auth OK on :$MGMT_PORT" "curl -sk --fail -u '$SPLUNK_USER:$SPLUNK_PASS' '$SPLUNK_MGMT_URL/services/server/info' >/dev/null 2>&1"

# --- 2. DefenseClaw gateway ----------------------------------------------
log "=== Stage 2: DefenseClaw gateway ==="
export DC_PORT
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-gw-rtr-$$}"
if curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1; then
  log "DefenseClaw already up on :$DC_PORT -> reusing"
  DC_UP=1
else
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
    log "WARN: DefenseClaw gateway failed to start; see $DC_OUT (proxy will fail-open)"
  fi
fi
check "DefenseClaw gateway healthy on :$DC_PORT" "[ ${DC_UP:-0} -eq 1 ]"
export SPLUNK_MGMT_URL SPLUNK_USER SPLUNK_PASS SPLUNK_INDEX

# --- 3. Lemonade (reuse-or-boot) -----------------------------------------
log "=== Stage 3: Lemonade $LEMON_MODEL on CPU (:$LEMONADE_PORT) — local tier ==="
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

# --- 4. semantic-router classify API -------------------------------------
log "=== Stage 4: semantic-router classify API (:$ROUTER_API_PORT) ==="
ROUTER_UP=0
if curl -sf "$ROUTER_URL/health" >/dev/null 2>&1 || router_wait; then
  log "router classify API already reachable -> reusing"
  ROUTER_UP=1
elif [ ! -x "$ROUTER_REPO_DIR/bin/router" ]; then
  log "FATAL(soft): $ROUTER_REPO_DIR/bin/router not found."
  log "  Build the vLLM semantic-router first (clone github.com/vllm-project/semantic-router into \$ROUTER_REPO_DIR and 'make build'), or set ROUTER_REPO_DIR."
else
  ROUT_LOG="$ART/router.log"; : > "$ROUT_LOG"
  # Newer router binaries run ensureModelsDownloadedOrFatal at startup, which
  # shells out to `huggingface-cli`. Make sure it's on PATH (reuse a venv's copy
  # if the base env doesn't have it) so the router doesn't fatally exit.
  HF_CLI_DIR=""
  if ! command -v huggingface-cli >/dev/null 2>&1; then
    for c in "$HOME/vllm-venv/bin/huggingface-cli" "$HOME/headroom-venv/bin/huggingface-cli"; do
      [ -x "$c" ] && { HF_CLI_DIR="$(dirname "$c")"; break; }
    done
  fi
  (
    cd "$ROUTER_REPO_DIR"
    [ -n "$HF_CLI_DIR" ] && export PATH="$HF_CLI_DIR:$PATH"
    export LD_LIBRARY_PATH="$PWD/candle-binding/target/release:$PWD/ml-binding/target/release:$PWD/nlp-binding/target/release:${LD_LIBRARY_PATH:-}"
    exec ./bin/router -config="$HERE/config.yaml" -api-port="$ROUTER_API_PORT" \
      -port="$ROUTER_EXTPROC_PORT" -metrics-port="$ROUTER_METRICS_PORT"
  ) >"$ROUT_LOG" 2>&1 &
  PIDS+=("$!")
  router_wait && ROUTER_UP=1
fi
check "semantic-router classify API healthy on :$ROUTER_API_PORT" "[ ${ROUTER_UP:-0} -eq 1 ]"
# Capture a sample classification for the artifacts (proves the API shape).
if [ "$ROUTER_UP" -eq 1 ]; then
  curl -s -m 10 -X POST "$ROUTER_URL/api/v1/classify/intent" -H 'content-type: application/json' \
    -d '{"text":"Prove that the square root of 2 is irrational, showing every step."}' \
    > "$ART/classify_sample.json" 2>&1 || true
  sed -n '1,20p' "$ART/classify_sample.json" 2>/dev/null
fi

# --- 5. frontier preflight -----------------------------------------------
log "=== Stage 5: frontier preflight ($FRONTIER_MODEL @ $FRONTIER_UPSTREAM) ==="
FRONTIER_READY=0
if [ -n "$FRONTIER_AUTH_KEY" ]; then
  curl -sS -m 60 "$FRONTIER_UPSTREAM/v1/messages" \
    -H 'content-type: application/json' \
    -H 'anthropic-version: 2023-06-01' \
    -H "$FRONTIER_AUTH_HEADER: $FRONTIER_AUTH_KEY" \
    -d "{\"model\":\"$FRONTIER_MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly: FRONTIER_OK\"}]}" \
    > "$ART/frontier_preflight.json" 2>"$ART/frontier_preflight.err" || true
  if grep -qE '"type"[[:space:]]*:[[:space:]]*"message"|"content"|"text"' "$ART/frontier_preflight.json"; then
    FRONTIER_READY=1
  fi
  check "frontier tier reachable (real completion)" "[ $FRONTIER_READY -eq 1 ]"
else
  log "no frontier key (GATEWAY_KEY/ANTHROPIC_API_KEY/FRONTIER_AUTH_KEY) -> frontier tier UNAVAILABLE"
  log "  router-on will still HARD-prove the DECISION (classification) but serve local (fail-safe)."
fi

# --- 6. BASELINE (router off) --------------------------------------------
log "=== Stage 6: BASELINE proxy (LEMON_ROUTER=off, session router-baseline) ==="
BASE_OK=0
if [ "${LEMON_UP:-0}" -eq 1 ] && start_proxy "router-baseline" "$PROXY_BASELINE_PORT" "baseline" "off"; then
  PROXY_BASELINE_URL="$PROXY_URL"
  log "baseline proxy up: $PROXY_BASELINE_URL"
  BASE_OK=1
  check "baseline proxy healthy" "true"
else
  log "WARN: baseline proxy failed to come up; see proxy_baseline.log"
  check "baseline proxy healthy" "false"
fi

# --- 7. ROUTER-ON --------------------------------------------------------
log "=== Stage 7: ROUTER-ON proxy (LEMON_ROUTER=on, session router-on) ==="
ROUTER_ON_OK=0
if [ "${LEMON_UP:-0}" -eq 1 ] && start_proxy "router-on" "$PROXY_ROUTER_PORT" "routeron" "on"; then
  PROXY_ROUTER_URL="$PROXY_URL"
  log "router-on proxy up: $PROXY_ROUTER_URL"
  ROUTER_ON_OK=1
  check "router-on proxy healthy" "true"
else
  log "WARN: router-on proxy failed to come up; see proxy_routeron.log"
  check "router-on proxy healthy" "false"
fi

# --- run the A/B probe against both proxies ------------------------------
ROUTING_CORRECT="n/a"
if [ "$BASE_OK" -eq 1 ] && [ "$ROUTER_ON_OK" -eq 1 ]; then
  log "=== running A/B probe (baseline vs router-on) ==="
  python3 "$HERE/router_ab_probe.py" \
    --baseline-url "$PROXY_BASELINE_URL" \
    --router-url "$PROXY_ROUTER_URL" \
    --model "$LEMON_MODEL" \
    --mode ab --timeout 300 --max-tokens 128 \
    --json-out "$ART/ab_results.json" > "$ART/ab_run.txt" 2>&1 || true
  sed -n '1,80p' "$ART/ab_run.txt"
  ROUTING_CORRECT="$(grep -oE 'routing correctness \(router-on\): [0-9]+/[0-9]+' "$ART/ab_run.txt" | grep -oE '[0-9]+/[0-9]+' | tail -1)"
  [ -z "$ROUTING_CORRECT" ] && ROUTING_CORRECT="0/0"

  # header-level A/B assertions (from the probe json)
  check "[headers] baseline kept every prompt local" \
    "python3 -c \"import json,sys; d=json.load(open('$ART/ab_results.json')); b=[v for k,v in d.items() if 'BASELINE' in k][0]; sys.exit(0 if all(r['tier']=='local' for r in b['results'] if r['ok']) and b['ok']>0 else 1)\""
  check "[headers] router-on routed all 7 prompts to the expected tier (decision)" \
    "python3 -c \"import json,sys; d=json.load(open('$ART/ab_results.json')); r=[v for k,v in d.items() if 'ROUTER-ON' in k][0]; exp={'simple':'local','reasoning':'frontier'}; sys.exit(0 if r['ok']==7 and all(x['decision_tier']==exp[x['expected_domain']] for x in r['results']) else 1)\""
fi

# --- HARD Splunk proofs --------------------------------------------------
log "=== Stage 6/7 HARD proof: routing events read back from index=$SPLUNK_INDEX ==="
# BASELINE: llm.request present with routing.enabled=false.
check "[baseline] llm.request CONFIRMED in Splunk (session router-baseline)" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-baseline event=llm.request' 1"
check "[baseline] routing block shows router DISABLED (routing.enabled=false)" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-baseline event=llm.request routing.enabled=false' 1"

# ROUTER-ON: llm.request with an enabled routing block; a frontier DECISION on
# the hard prompts (selected_model=claude-*); and, if a key is present, an actual
# frontier-tier escalation.
check "[router-on] llm.request CONFIRMED in Splunk (session router-on)" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-on event=llm.request' 1"
check "[router-on] routing block shows router ENABLED + reachable" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-on event=llm.request routing.enabled=true routing.reachable=true' 1"
check "[router-on] a HARD prompt got a FRONTIER decision (routing.selected_model=claude-*)" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-on event=llm.request routing.selected_model=claude-*' 1"
check "[router-on] a SIMPLE prompt stayed LOCAL (routing.tier=local)" \
  "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-on event=llm.request routing.tier=local' 1"
if [ "$FRONTIER_READY" -eq 1 ]; then
  check "[router-on] a HARD prompt ESCALATED to the frontier tier (routing.tier=frontier)" \
    "splunk_wait 'search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=router-on event=llm.request routing.tier=frontier' 1"
else
  log "SKIP frontier-tier escalation assertion (no key) — decision proven via routing.selected_model=claude-*"
fi

# --- 8. Claude Code THROUGH the router-on proxy (best-effort) -------------
CC_STATUS="skip"
if [ "${RUN_CC:-1}" -eq 1 ] && command -v claude >/dev/null 2>&1 && [ "${LEMON_UP:-0}" -eq 1 ]; then
  log "=== Stage 8: Claude Code THROUGH the router-on proxy (session cc-router) ==="
  if start_proxy "cc-router" "$PROXY_CC_PORT" "cc" "on"; then
    PROXY_CC_URL="$PROXY_URL"; PROXY_CC_PID="${PIDS[-1]}"
    GATEWAY_URL="$PROXY_CC_URL" MODEL="$LEMON_MODEL" \
      bash "$HERE/claude_job.sh" 'Reply with exactly: ROUTER_CC_OK' \
      > "$ART/claude_cc.out" 2>"$ART/claude_cc.err" || true
    if splunk_wait "search index=$SPLUNK_INDEX sourcetype=axis:llm | spath | search identity.session=cc-router event=llm.request routing.enabled=true" 1; then
      CC_STATUS="ok"
      check "[cc] Claude Code produced an llm.request with a routing block (session cc-router)" "true"
    else
      log "SKIP: Claude Code did not drive a confirmable llm.request (weak local model); see claude_cc.err"
    fi
    [ -n "${PROXY_CC_PID:-}" ] && stop_proxy "$PROXY_CC_PID"
  else
    log "SKIP: cc proxy failed to come up"
  fi
else
  log "SKIP Stage 8: RUN_CC=0 / claude missing / Lemonade down"
fi

# --- 9. summary -----------------------------------------------------------
log "=== Dumping the Splunk index (search API) -> artifacts/splunk_query.txt ==="
SPLUNK_MGMT_URL="$SPLUNK_MGMT_URL" SPLUNK_USER="$SPLUNK_USER" SPLUNK_PASS="$SPLUNK_PASS" \
  SPLUNK_INDEX="$SPLUNK_INDEX" EARLIEST="-1h" \
  bash "$SPLUNK_TEST/query_splunk.sh" > "$ART/splunk_query.txt" 2>&1 || true
sed -n '1,40p' "$ART/splunk_query.txt" 2>/dev/null

log "=== RESULT: $pass passed, $fail failed ==="
{
  echo "router_test run @ $(date -u +%FT%TZ)"
  echo "host=$(hostname) node=$(node --version)"
  echo "inference: proxy -> Lemonade $LEMON_MODEL (local :$LEMONADE_PORT) | frontier $FRONTIER_MODEL @ $FRONTIER_UPSTREAM"
  echo "router: classify API :$ROUTER_API_PORT (consult-only); toggle=LEMON_ROUTER"
  echo "audit: real Splunk index=$SPLUNK_INDEX sourcetype=axis:llm (routing block)"
  echo "splunk_up=${SPLUNK_UP:-0} defenseclaw_up=${DC_UP:-0} lemonade_up=${LEMON_UP:-0} router_up=${ROUTER_UP:-0} frontier_ready=${FRONTIER_READY:-0}"
  echo "routing_correct=${ROUTING_CORRECT}"
  echo "pass=$pass fail=$fail"
  echo "cc=$CC_STATUS"
} > "$ART/SUMMARY.txt"
cat "$ART/SUMMARY.txt"
[ "$fail" -eq 0 ]
