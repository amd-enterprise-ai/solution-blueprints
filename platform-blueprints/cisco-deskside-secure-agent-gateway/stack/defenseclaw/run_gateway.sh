#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# run_gateway.sh — build (if needed) and run the real Cisco DefenseClaw gateway
# sidecar on :18970 for the client-side integration.
#
# The gateway is the Go binary `defenseclaw-gateway` (cmd/defenseclaw). Run with
# no args it starts the sidecar daemon and exposes the local REST API the
# connector talks to: POST /api/v1/inspect/tool returns an allow/block verdict
# for each tool call. We point its $DEFENSECLAW_HOME at a scratch dir seeded
# with defenseclaw.policy.yaml (guardrail.mode=action) so HIGH/CRITICAL findings
# actually block.
#
# Env:
#   DC_REPO        path to the defenseclaw checkout   (default: $HOME/repos/defenseclaw;
#                  clone from https://github.com/cisco-ai-defense/defenseclaw)
#   DEFENSECLAW_HOME  gateway data dir                 (default: mktemp)
#   DC_PORT        REST API port                       (default: 18970)
#   DC_LOG         gateway log file                    (default: $DEFENSECLAW_HOME/gateway.log)
#   GOBIN/PATH     a Go toolchain (>=1.26) must be on PATH; we try to install via
#                  the system pkg manager only if `go` is missing.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DC_REPO="${DC_REPO:-$(cd "$HERE/../../../repos/defenseclaw" 2>/dev/null && pwd || echo "$HOME/repos/defenseclaw")}"
DC_PORT="${DC_PORT:-18970}"
DEFENSECLAW_HOME="${DEFENSECLAW_HOME:-$(mktemp -d "${TMPDIR:-/tmp}/dc_home.XXXXXX")}"
DC_LOG="${DC_LOG:-$DEFENSECLAW_HOME/gateway.log}"
export DEFENSECLAW_HOME

# Gateway auth token. DefenseClaw >=0.8 fails closed: every REST route except
# GET /health requires a Bearer token. If the caller didn't pin one, mint a
# stable token here and export it so (a) the gateway adopts it at boot
# (EnsureGatewayToken honours $DEFENSECLAW_GATEWAY_TOKEN) and (b) the connector
# can authenticate. We print it so run_integration.sh can forward it.
export DEFENSECLAW_GATEWAY_TOKEN="${DEFENSECLAW_GATEWAY_TOKEN:-cs-$(date +%s)-$$}"

say(){ printf '\n[gateway] %s\n' "$*"; }

if [ -z "${DC_REPO:-}" ] || [ ! -d "$DC_REPO" ]; then
  echo "[gateway] FATAL: defenseclaw repo not found (set DC_REPO)"; exit 2
fi

# --- ensure a Go toolchain ------------------------------------------------
if ! command -v go >/dev/null 2>&1; then
  say "Go not found; attempting install"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y golang-go
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y golang
  elif command -v brew >/dev/null 2>&1; then
    brew install go
  fi
fi
command -v go >/dev/null 2>&1 || { echo "[gateway] FATAL: Go toolchain required"; exit 2; }
say "go: $(go version)"

# --- build the gateway binary ---------------------------------------------
# Build through `make gateway`, NOT a raw `go build`. The gateway embeds an
# OpenClaw plugin tree via //go:embed all:openclaw_extension; on a fresh clone
# that directory doesn't exist and the build fails with:
#   internal/gateway/connector/openclaw.go:42: pattern all:openclaw_extension:
#   no matching files found
# The `sync-openclaw-extension` prerequisite (run by `make gateway`) drops a
# .placeholder so //go:embed has an entry — we don't need the real OpenClaw
# plugin since this connector only uses the gateway's REST inspect API.
GW_BIN="$DC_REPO/defenseclaw-gateway"
if [ ! -x "$GW_BIN" ]; then
  say "building defenseclaw-gateway via 'make gateway' (this can take a minute)"
  if command -v make >/dev/null 2>&1; then
    ( cd "$DC_REPO" && make gateway ) \
      || { echo "[gateway] FATAL: make gateway failed"; exit 2; }
  else
    # No make: replicate the placeholder drop, then go build directly.
    EMBED_DIR="$DC_REPO/internal/gateway/connector/openclaw_extension"
    if [ ! -e "$EMBED_DIR/.placeholder" ] && [ -z "$(ls -A "$EMBED_DIR" 2>/dev/null)" ]; then
      mkdir -p "$EMBED_DIR"
      printf 'OpenClaw extension not built.\n' > "$EMBED_DIR/.placeholder"
    fi
    ( cd "$DC_REPO" && go build -o defenseclaw-gateway ./cmd/defenseclaw ) \
      || { echo "[gateway] FATAL: go build failed"; exit 2; }
  fi
fi
say "binary: $GW_BIN"

# --- seed config (guardrail.mode=action, api_port) ------------------------
mkdir -p "$DEFENSECLAW_HOME"
cp "$HERE/defenseclaw.policy.yaml" "$DEFENSECLAW_HOME/config.yaml"
# The api_port can also be overridden to DC_PORT if the caller changed it.
if [ "$DC_PORT" != "18970" ]; then
  sed -i.bak "s/api_port: 18970/api_port: $DC_PORT/" "$DEFENSECLAW_HOME/config.yaml" || true
fi
say "config: $DEFENSECLAW_HOME/config.yaml (mode=action, api_port=$DC_PORT)"

# --- run the sidecar ------------------------------------------------------
say "starting gateway -> $DC_LOG"
"$GW_BIN" >"$DC_LOG" 2>&1 &
GW_PID=$!
echo "$GW_PID" > "$DEFENSECLAW_HOME/gateway.pid"

# --- wait for health ------------------------------------------------------
for _ in $(seq 1 100); do
  curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1 && break
  kill -0 "$GW_PID" 2>/dev/null || { echo "[gateway] FATAL: process died; log:"; cat "$DC_LOG"; exit 2; }
  sleep 0.2
done
if curl -sf "http://127.0.0.1:$DC_PORT/health" >/dev/null 2>&1; then
  say "healthy on :$DC_PORT (pid $GW_PID)"
  echo "DEFENSECLAW_HOME=$DEFENSECLAW_HOME"
  echo "GATEWAY_PID=$GW_PID"
  echo "DEFENSECLAW_GATEWAY_TOKEN=$DEFENSECLAW_GATEWAY_TOKEN"
else
  echo "[gateway] FATAL: did not become healthy; log:"; cat "$DC_LOG"; exit 2
fi

# If run directly (not sourced), wait so the process stays in the foreground.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  wait "$GW_PID"
fi
