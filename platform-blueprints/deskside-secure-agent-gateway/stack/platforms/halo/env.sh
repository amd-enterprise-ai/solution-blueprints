#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# platforms/halo/env.sh — source this to run gateway on a Strix Halo
# deskside. Repo-relative and self-locating: no per-user paths are hardcoded.
#
#   source stack/platforms/halo/env.sh
#   bash   stack/platforms/halo/run.sh          # functional loop
#   REDTEAM_MODE=regression bash stack/run_redteam.sh
#
# The heavy toolchain (Go, Rust, the built AXIS + DefenseClaw binaries) lives
# OUTSIDE the repo under $HALO_TOOLS (built by platforms/halo/setup.sh). Override HALO_TOOLS
# to relocate it. Safe to source multiple times.

HALO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Toolchain root (built artifacts, not committed to the repo).
export HALO_TOOLS="${HALO_TOOLS:-$HOME/halo-toolchain}"

# Isolated Go / Rust caches under the toolchain root.
export GOPATH="$HALO_TOOLS/gopath"
export GOCACHE="$HALO_TOOLS/gocache"
export GOMODCACHE="$HALO_TOOLS/gopath/pkg/mod"
export RUSTUP_HOME="$HALO_TOOLS/rustup"
export CARGO_HOME="$HALO_TOOLS/cargo"

# node from nvm (already on the box).
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1

# PATH: built axis bin dir first, then Go, then Rust/cargo, then the lemonade
# venv bin (Lemonade is pip-installed into $HALO_TOOLS/lemon-venv on this box
# because python3-venv/system packages need sudo; the venv provides
# lemonade-server -> lemonade-server-dev).
export PATH="$HALO_TOOLS/bin:$HALO_TOOLS/go/bin:$CARGO_HOME/bin:$HALO_TOOLS/lemon-venv/bin:$PATH"

# Lemonade needs an exec-capable temp dir; /tmp is mounted noexec on this box.
export TMPDIR="${TMPDIR:-$HALO_TOOLS/tmp}"
mkdir -p "$TMPDIR" 2>/dev/null || true

# AXIS: the unprivileged native policy that ships with the repo (Halo target).
export AXIS_BIN="axis"
export AXIS_POLICY="$HALO_DIR/axis-policy-native.yaml"

# Deskside hardening (see REDTEAM_FINDINGS.md): fail-closed audit is on by
# default on the real deskside; the userspace fork-bomb cap is sized above the
# live thread baseline so legit forks are unaffected.
export AUDIT_REQUIRED="${AUDIT_REQUIRED:-1}"
export AXIS_ULIMIT_NPROC="${AXIS_ULIMIT_NPROC:-$(( $(ps -eLf -u "$USER" 2>/dev/null | wc -l) + 4096 ))}"

# Ports (override if occupied on the shared box).
export DC_PORT="${DC_PORT:-18970}"
export HEC_PORT="${HEC_PORT:-18088}"
export LEMONADE_PORT="${LEMONADE_PORT:-13305}"
export PROXY_PORT="${PROXY_PORT:-13399}"
