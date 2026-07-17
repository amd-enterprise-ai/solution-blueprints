#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Tokenomics A/B — τ-bench × vLLM semantic router on Strix Halo.
#
# ARM A (router-on):  τ-bench agent LLM calls → lemonade_proxy (LEMON_ROUTER=on)
#   → semantic router classifies each prompt → local Qwen3-Coder-30B or frontier
#   Opus 4.8 (AMD Gateway).
# ARM B (frontier-only): τ-bench agent LLM calls → lemonade_proxy
#   (LEMON_FORCE_FRONTIER=1) → every call → Opus 4.8.
#
# Both arms run the SAME 50 tasks (25 retail + 25 airline).
# τ-bench uses litellm with ANTHROPIC provider, which reads ANTHROPIC_BASE_URL
# automatically — zero harness modifications needed.
#
# Env (required):
#   GATEWAY_KEY   — AMD gateway Ocp-Apim-Subscription-Key (32-char)
# Env (optional):
#   ARMS                        "A B" (default both)
#   CC_TIMEOUT                  per-task timeout seconds (default 300)
#   MAX_TURNS                   tau_bench max_turns (default 20)
#   LEMONADE_PORT               (default 13305)
#   LEMON_ROUTER_CLASSIFY_INPUT last_user (default) | full — which text the router
#                               classifies (last user turn vs whole flattened prompt)
#   ROUTER_CLASSIFY_TIMEOUT_MS  router classify timeout (default: proxy default 5s)
#   ROUTER_CPUS                 taskset core range for the router (e.g. 448-511);
#                               empty = no pinning. On CPU-only nodes, pin the
#                               router off the local-inference cores so its
#                               embedding classify is never starved (otherwise it
#                               times out and fails open to local).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSI="$(cd "$HERE/../../stack" && pwd)"
# ROUTER_REPO: clone https://github.com/vllm-project/semantic-router and build it first.
ROUTER_REPO="${ROUTER_REPO:-$HOME/repos/semantic-router}"
# TAUBENCH: clone https://github.com/sierra-research/tau-bench first.
TAUBENCH="${TAUBENCH:-$(cd "$HERE/../../../repos/tau-bench" 2>/dev/null && pwd || echo "$HOME/repos/tau-bench")}"
ART="${ART:-$HERE/artifacts}"; mkdir -p "$ART"

# Toolchain root — override HALO_TOOLS to relocate (default: $HOME/halo-toolchain).
HALO_TOOLS="${HALO_TOOLS:-$HOME/halo-toolchain}"
PY="${PY:-$HALO_TOOLS/lemon-venv/bin/python}"

export TMPDIR="${TMPDIR:-$HALO_TOOLS/tmp}"; mkdir -p "$TMPDIR"
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE" CURL_CA_BUNDLE="$SSL_CERT_FILE"
export NODE_EXTRA_CA_CERTS="$SSL_CERT_FILE"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
nvm use 22 >/dev/null 2>&1 || true
export PATH="$HALO_TOOLS/lemon-venv/bin:$HALO_TOOLS/bin:$PATH"

ARMS="${ARMS:-A B}"
CC_TIMEOUT="${CC_TIMEOUT:-300}"  # per-env timeout (retail 25 tasks + airline 25 tasks)
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
PROXY_PORT="${PROXY_PORT:-13399}"
ROUTER_PORT="${ROUTER_PORT:-18099}"
FRONTIER_MODEL="${FRONTIER_MODEL:-claude-opus-4-8}"
FRONTIER_URL="${FRONTIER_URL:-https://<llm-gateway>/Anthropic}"
LOCAL_MODEL="${LOCAL_MODEL:-Qwen3-Coder-30B-A3B-Instruct-GGUF}"
GATEWAY_KEY="${GATEWAY_KEY:?GATEWAY_KEY required (AMD gateway key)}"

log(){ echo "[tau-tokenomics $(date +%H:%M:%S)] $*"; }

# Load task indices
RETAIL_IDS=$(python3 -c "import json;d=json.load(open('$HERE/data/tasks_retail.json'));print(' '.join(str(i) for i in d['indices']))")
AIRLINE_IDS=$(python3 -c "import json;d=json.load(open('$HERE/data/tasks_airline.json'));print(' '.join(str(i) for i in d['indices']))")

PIDS=()
PROXY_PID=""
cleanup(){
  [ -n "$PROXY_PID" ] && kill "$PROXY_PID" 2>/dev/null
  for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
}
trap cleanup EXIT

# --- start router (shared by arm A) ----------------------------------------
start_router(){
  ss -ltn 2>/dev/null | grep -q ":$ROUTER_PORT " && { log "router already on :$ROUTER_PORT"; return 0; }
  log "starting semantic router on :$ROUTER_PORT"
  # Optional CPU pinning (ROUTER_CPUS, e.g. "448-511"): on CPU-only nodes the
  # local llama.cpp backend can grab every core and starve the router's embedding
  # classify, which then times out and fails open to local. Pinning the router to
  # a dedicated core range keeps classify fast. Empty (default) => no pinning.
  local pin=(); [ -n "${ROUTER_CPUS:-}" ] && pin=(taskset -c "$ROUTER_CPUS")
  ( cd "$ROUTER_REPO" && \
    LD_LIBRARY_PATH="$ROUTER_REPO/candle-binding/target/release:$ROUTER_REPO/nlp-binding/target/release:$ROUTER_REPO/ml-binding/target/release" \
    "${pin[@]}" ./bin/router -config "$HERE/router/config.yaml" -api-port "$ROUTER_PORT" -enable-api ) \
    >"$ART/router.log" 2>&1 &
  PIDS+=("$!")
  for _ in $(seq 1 90); do grep -q 'startup_complete' "$ART/router.log" 2>/dev/null && break; sleep 2; done
  for _ in $(seq 1 60); do
    curl -sf --max-time 15 "http://127.0.0.1:$ROUTER_PORT/api/v1/classify/intent" \
      -H 'content-type: application/json' -d '{"text":"book a flight from NYC to LA"}' 2>/dev/null \
      | grep -q 'routing_decision' && { log "router classify ready"; return 0; }
    sleep 2
  done
  log "WARN: router classify not ready"; return 1
}

# --- start proxy for an arm -------------------------------------------------
start_proxy(){
  local arm="$1" sess="$2" audit_db="$3"
  [ -n "$PROXY_PID" ] && kill "$PROXY_PID" 2>/dev/null; sleep 1
  local router_env=()
  if [ "$arm" = "A" ]; then
    router_env=( LEMON_ROUTER=on SEMANTIC_ROUTER_URL="http://127.0.0.1:$ROUTER_PORT" )
  else
    router_env=( LEMON_ROUTER=off LEMON_FORCE_FRONTIER=1 )
  fi
  AXIS_SESSION="$sess" LEMON_PROXY_PORT="$PROXY_PORT" \
  LEMON_UPSTREAM="http://127.0.0.1:$LEMONADE_PORT" LEMON_MODEL="$LOCAL_MODEL" \
  LEMON_TRANSLATE_LOCAL="${LEMON_TRANSLATE_LOCAL:-1}" \
  LEMON_ROUTER_CLASSIFY_INPUT="${LEMON_ROUTER_CLASSIFY_INPUT:-last_user}" \
  ROUTER_CLASSIFY_TIMEOUT_MS="${ROUTER_CLASSIFY_TIMEOUT_MS:-}" \
  FRONTIER_UPSTREAM="$FRONTIER_URL" FRONTIER_MODEL="$FRONTIER_MODEL" \
  FRONTIER_AUTH_HEADER="Ocp-Apim-Subscription-Key" FRONTIER_AUTH_KEY="$GATEWAY_KEY" \
  FRONTIER_EXTRA_HEADERS='{"anthropic-version":"2023-06-01"}' \
  AUDIT_DB="$audit_db" \
    env "${router_env[@]}" node "$CSI/lemonade_proxy/src/server.js" \
    >"$ART/proxy_$arm.log" 2>&1 &
  PROXY_PID=$!; PIDS+=("$PROXY_PID")
  for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$PROXY_PORT/api/v1/health" >/dev/null 2>&1 && \
    { log "proxy ($arm) up on :$PROXY_PORT"; return 0; }; sleep 0.5; done
  log "FATAL: proxy ($arm) failed; see $ART/proxy_$arm.log"; return 1
}

# --- run tau-bench tasks for one env ----------------------------------------
run_env(){
  local arm="$1" env_name="$2" task_ids="$3" out_dir="$4"
  mkdir -p "$out_dir"
  log "  [$arm] env=$env_name tasks=$task_ids"
  unset ANTHROPIC_CUSTOM_HEADERS
  # Opus 4.8 rejects temperature=0.0 (tau-bench default); drop it via litellm.
  # temperature=1 is the only supported value for Opus 4 models.
  ANTHROPIC_BASE_URL="http://127.0.0.1:$PROXY_PORT" \
  ANTHROPIC_API_KEY="tokenomics-local" \
  LITELLM_SSL_VERIFY=false \
  LITELLM_DROP_PARAMS=true \
    timeout "$((CC_TIMEOUT * 50))" \
    "$PY" "$TAUBENCH/run.py" \
      --env "$env_name" \
      --model "$FRONTIER_MODEL" \
      --model-provider anthropic \
      --user-model "$FRONTIER_MODEL" \
      --user-model-provider anthropic \
      --user-strategy llm \
      --agent-strategy tool-calling \
      --temperature 1 \
      --task-ids $task_ids \
      --max-concurrency 1 \
      --log-dir "$out_dir" \
      </dev/null \
      >"$ART/taubench_${arm}_${env_name}.log" 2>&1 || true
}

# --- main -------------------------------------------------------------------
log "preflight: Lemonade :$LEMONADE_PORT"
curl -sf "http://127.0.0.1:$LEMONADE_PORT/api/v1/health" >/dev/null 2>&1 \
  || { log "FATAL: Lemonade not healthy"; exit 2; }

[[ "$ARMS" == *A* ]] && start_router || true

for arm in $ARMS; do
  log "=== ARM $arm ($([ "$arm" = A ] && echo router-on || echo frontier-only)) ==="
  audit_db="$ART/audit_$arm.db"; rm -f "$audit_db"
  sink="$ART/events_$arm.jsonl"
  start_proxy "$arm" "tau-$arm" "$audit_db" || continue

  run_env "$arm" "retail"  "$RETAIL_IDS"  "$ART/results_${arm}_retail"
  run_env "$arm" "airline" "$AIRLINE_IDS" "$ART/results_${arm}_airline"

  [ -n "$PROXY_PID" ] && kill "$PROXY_PID" 2>/dev/null; PROXY_PID=""; sleep 1
  # Export the SQLite audit rows to newline-delimited JSON for analyze.py.
  "$PY" -c "
import sqlite3, sys
db = sqlite3.connect('$audit_db')
for (data,) in db.execute('SELECT data FROM events ORDER BY id'):
    print(data)
db.close()
" > "$sink" 2>/dev/null || : > "$sink"
  n_events=$(grep -c '"event":"llm.request"' "$sink" 2>/dev/null || echo 0)
  log "ARM $arm done: $n_events llm.request events"
done

log "=== analysis ==="
"$PY" "$HERE/analyze.py" \
  "$ART/events_A.jsonl" "$ART/events_B.jsonl" \
  "$ART/results_A_retail" "$ART/results_A_airline" \
  "$ART/results_B_retail" "$ART/results_B_airline" \
  > "$ART/SUMMARY.txt" 2>"$ART/analyze.err" || true
cat "$ART/SUMMARY.txt"
log "DONE. events: $ART/events_{A,B}.jsonl  summary: $ART/SUMMARY.txt"
