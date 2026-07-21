#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# platforms/halo/setup.sh — one-shot, idempotent toolchain bring-up for
# gateway on a Strix Halo deskside (or any clean Ubuntu box).
# Re-running is safe. Everything is installed under $HALO_TOOLS and does NOT
# touch shared system paths, sudo, or the account's dotfiles.
#
#   source stack/platforms/halo/env.sh   # sets HALO_TOOLS, paths
#   bash   stack/platforms/halo/setup.sh
#   bash   stack/platforms/halo/run.sh
#
# The AXIS policy is the committed platforms/halo/axis-policy-native.yaml — this
# script only builds the external binaries (Go, Rust, AXIS) that can't live in
# the repo.
set -euo pipefail

HALO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSI="$(dirname "$(dirname "$HALO_DIR")")"   # .../stack (halo lives under platforms/)
source "$HALO_DIR/env.sh"

GO_VERSION="${GO_VERSION:-1.26.4}"
# Build AXIS from ROCm/axis, pinned to a validated commit so the build is
# reproducible and never tracks a moving branch. Override with AXIS_REF/AXIS_REPO.
AXIS_REPO="${AXIS_REPO:-https://github.com/ROCm/axis.git}"
AXIS_REF="${AXIS_REF:-0224ab0268c09ad862cf73e1bec66e44a0979195}"
say(){ printf '\n\033[1;36m[halo-setup]\033[0m %s\n' "$*"; }
have(){ command -v "$1" >/dev/null 2>&1; }

mkdir -p "$HALO_TOOLS"/{repos,bin,gopath,gocache}
chmod 755 "$HALO_TOOLS" "$HALO_TOOLS/bin"   # axis rejects a group/world-writable launcher dir

have node || { echo "FATAL: node not found (expected via nvm)"; exit 2; }
# npm ships WITH Node; if it is missing the box has a partial/system Node without
# npm on PATH. Fail fast here rather than deep inside the first `npm install`.
have npm || { echo "FATAL: npm not found. Install Node via nvm (bundles npm) so 'npm' is on PATH: https://github.com/nvm-sh/nvm"; exit 2; }
say "node $(node --version) / npm $(npm --version)"

# --- Go --------------------------------------------------------------------
if [ "$("$HALO_TOOLS/go/bin/go" version 2>/dev/null | awk '{print $3}')" != "go${GO_VERSION}" ]; then
  say "installing Go ${GO_VERSION} -> $HALO_TOOLS/go"
  curl -fsSL -o /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
  rm -rf "$HALO_TOOLS/go" && tar -C "$HALO_TOOLS" -xzf /tmp/go.tgz && rm -f /tmp/go.tgz
else say "Go ${GO_VERSION} present"; fi
go version

# --- Rust ------------------------------------------------------------------
if ! have cargo; then
  say "installing Rust (rustup, minimal) -> $HALO_TOOLS/{rustup,cargo}"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal
else say "Rust present"; fi
cargo --version

# --- AXIS (public, build from source) -------------------------------------
if [ ! -d "$HALO_TOOLS/repos/axis/.git" ]; then
  say "cloning $AXIS_REPO"
  git clone --filter=blob:none "$AXIS_REPO" "$HALO_TOOLS/repos/axis"
fi
# Always (re)pin to AXIS_REF, even on reruns or when AXIS_REF is overridden, so the
# working tree matches the pinned commit rather than whatever it happened to be on.
( cd "$HALO_TOOLS/repos/axis" \
  && { git cat-file -e "${AXIS_REF}^{commit}" 2>/dev/null || git fetch --filter=blob:none origin "$AXIS_REF"; } \
  && git checkout --detach "$AXIS_REF" )
if [ ! -x "$HALO_TOOLS/bin/axis" ]; then
  say "building AXIS (cargo build --release; a few minutes)"
  ( cd "$HALO_TOOLS/repos/axis" && cargo build --release -p axis-cli -p axis-daemon -p axis-sandbox --bins )
  cp "$HALO_TOOLS/repos/axis/target/release/"{axis,axisd,axis-seccomp-launcher,axis-netns-helper} "$HALO_TOOLS/bin/"
  chmod 755 "$HALO_TOOLS/bin/"*
else say "AXIS present ($($HALO_TOOLS/bin/axis --version 2>/dev/null))"; fi

# --- lemonade-sdk (public, fallback build source) --------------------------
[ -d "$HALO_TOOLS/repos/lemonade-sdk/.git" ] || \
  git clone https://github.com/lemonade-sdk/lemonade.git "$HALO_TOOLS/repos/lemonade-sdk" || true

# --- repos/ symlinks so run_gateway.sh / run_lemonade.sh can find them -------
# Symlinks in both $HOME/repos and the legacy sibling path for compatibility.
say "linking repos into $HOME/repos"
mkdir -p "$HOME/repos"
ln -sfn "$HALO_TOOLS/repos/lemonade-sdk" "$HOME/repos/lemonade-sdk"

# --- npm deps + unit tests -------------------------------------------------
# Install ALL npm deps before running any unit test. The connector's
# sqlite_events.test.js imports ../shared/sqlite_sink.js, which requires
# better-sqlite3 to be resolvable from $CSI/node_modules (the stack root). If the
# connector test runs before the root `npm install`, it fails with
# "Cannot find package 'better-sqlite3'" on a clean box and aborts setup.
say "installing npm deps"
( cd "$CSI/axis_mcp_connector" && npm install --no-audit --no-fund >/dev/null )
( cd "$CSI"                    && npm install --no-audit --no-fund >/dev/null )
( cd "$CSI/lemonade_proxy"     && npm install --no-audit --no-fund >/dev/null )
say "running unit tests"
( cd "$CSI/axis_mcp_connector" && node --test 2>&1 | grep -E '# (tests|pass|fail)' )
( cd "$CSI/lemonade_proxy"     && node --test 2>&1 | grep -E '# (tests|pass|fail)' )

# --- AXIS smoke test -------------------------------------------------------
say "AXIS smoke test (expect ROCM_OK)"
axis run --policy "$HALO_DIR/axis-policy-native.yaml" -- bash -c 'echo ROCM_OK' 2>/dev/null | grep -q ROCM_OK \
  && echo "  AXIS OK" || echo "  AXIS SMOKE FAILED — check policy/perms"

say "DONE. Now:  bash $HALO_DIR/run.sh"
