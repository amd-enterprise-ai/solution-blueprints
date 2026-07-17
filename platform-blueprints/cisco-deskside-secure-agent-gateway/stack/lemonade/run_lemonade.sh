#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_lemonade.sh — install + serve a 7B GGUF on CPU with Lemonade, and expose
# the Anthropic-compatible endpoint Claude Code talks to.
#
# Lemonade serves a quantized GGUF model locally (on the APU, or on CPU where no
# GPU backend is available) — entirely sufficient to prove the inference plane
# wiring (Claude Code -> Lemonade) since the tool/audit plane is backend-agnostic.
#
# Env:
#   LEMONADE_PORT   server port                 (default: 13305)
#   LEMON_MODEL     model to serve              (default: Qwen3-8B-GGUF)
#   LEMON_REPO      lemonade checkout (source build fallback)
#                   (default: $HOME/repos/lemonade-sdk;
#                    clone from https://github.com/lemonade-sdk/lemonade)
#   LEMON_LOG       server log                  (default: /tmp/lemonade.log)
#
# Prints, on success:
#   ANTHROPIC_BASE_URL=http://127.0.0.1:<port>
# which SETUP.md / run_integration.sh feed to Claude Code (with a dummy key).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEMONADE_PORT="${LEMONADE_PORT:-13305}"
LEMON_MODEL="${LEMON_MODEL:-Qwen3-8B-GGUF}"
LEMON_REPO="${LEMON_REPO:-$(cd "$HERE/../../../repos/lemonade-sdk" 2>/dev/null && pwd || echo "$HOME/repos/lemonade-sdk")}"
LEMON_LOG="${LEMON_LOG:-/tmp/lemonade.log}"
HEALTH="http://127.0.0.1:$LEMONADE_PORT/api/v1/health"

say(){ printf '\n[lemonade] %s\n' "$*"; }

# --- 1. ensure a lemonade server CLI is available -------------------------
have_server() { command -v lemonade-server >/dev/null 2>&1 || command -v lemond >/dev/null 2>&1; }

if ! have_server; then
  say "lemonade-server not found; installing"
  if command -v apt-get >/dev/null 2>&1; then
    # Debian Trixie+/Ubuntu ship a package.
    sudo apt-get update -y && sudo apt-get install -y lemonade-server || true
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y lemonade-server || true
  fi
fi

# Fallback: build from the cloned source (CMake C++ project).
if ! have_server; then
  if [ -n "${LEMON_REPO:-}" ] && [ -d "$LEMON_REPO" ]; then
    say "building lemonade from source at $LEMON_REPO"
    ( cd "$LEMON_REPO" && yes | ./setup.sh && cmake --build --preset default ) || true
    # Put the freshly built binaries on PATH for this script.
    [ -d "$LEMON_REPO/build" ] && export PATH="$LEMON_REPO/build:$PATH"
  fi
fi

if ! have_server; then
  echo "[lemonade] FATAL: could not install/build lemonade-server."
  echo "           Install manually: https://lemonade-server.ai/install_options.html#linux"
  exit 2
fi

SERVER_BIN="$(command -v lemonade-server || command -v lemond)"
CLI_BIN="$(command -v lemonade || echo "$SERVER_BIN")"
say "server: $SERVER_BIN"

# --- 2. start the server --------------------------------------------------
if ! curl -sf "$HEALTH" >/dev/null 2>&1; then
  say "starting server on :$LEMONADE_PORT -> $LEMON_LOG"
  if [[ "$SERVER_BIN" == *lemonade-server ]]; then
    LEMONADE_PORT="$LEMONADE_PORT" "$SERVER_BIN" serve --port "$LEMONADE_PORT" >"$LEMON_LOG" 2>&1 &
  else
    LEMONADE_PORT="$LEMONADE_PORT" "$SERVER_BIN" --port "$LEMONADE_PORT" >"$LEMON_LOG" 2>&1 &
  fi
  echo $! > /tmp/lemonade.pid
fi

for _ in $(seq 1 150); do
  curl -sf "$HEALTH" >/dev/null 2>&1 && break; sleep 0.4
done
curl -sf "$HEALTH" >/dev/null 2>&1 || { echo "[lemonade] FATAL: server not healthy; log:"; tail -40 "$LEMON_LOG" 2>/dev/null; exit 2; }
say "server healthy ($HEALTH)"

# --- 3. pull + load the 7B GGUF (CPU) -------------------------------------
say "pulling + loading $LEMON_MODEL on CPU (first pull downloads weights; slow)"
LEMONADE_PORT="$LEMONADE_PORT" "$CLI_BIN" pull "$LEMON_MODEL" >>"$LEMON_LOG" 2>&1 || \
  say "pull returned non-zero (model may already be present); continuing"
# Load it into a server slot so the first request doesn't time out.
curl -sf -X POST "http://127.0.0.1:$LEMONADE_PORT/api/v1/load" \
  -H 'content-type: application/json' \
  -d "{\"model_name\":\"$LEMON_MODEL\"}" >/dev/null 2>&1 || true

say "READY"
echo "ANTHROPIC_BASE_URL=http://127.0.0.1:$LEMONADE_PORT"
echo "LEMON_MODEL=$LEMON_MODEL"
