#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# platforms/halo/run.sh — run the gateway functional loop on Strix Halo,
# with the deskside environment this box needs. Assumes platforms/halo/setup.sh has run.
#
#   bash stack/platforms/halo/run.sh            # baseline (RUN_CC=0)
#   RUN_CC=1 bash stack/platforms/halo/run.sh   # + best-effort Claude Code
set -uo pipefail

HALO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSI="$(dirname "$(dirname "$HALO_DIR")")"   # .../stack (halo lives under platforms/)
source "$HALO_DIR/env.sh"
export RUN_CC="${RUN_CC:-0}"

# preflight: warn if our ports are already taken (shared-box etiquette)
busy=""
for p in "$PROXY_PORT"; do
  ss -ltn 2>/dev/null | grep -q ":$p " && busy="$busy $p"
done
if [ -n "$busy" ]; then
  echo "WARNING: port(s) in use:$busy — override e.g. PROXY_PORT=23399 bash platforms/halo/run.sh"
fi

echo "== running run_integration.sh on $(hostname) (RUN_CC=$RUN_CC, axis=$(command -v axis)) =="
cd "$CSI"
bash run_integration.sh
code=$?
echo "== exit=$code =="; echo "== SUMMARY =="; cat "$CSI/artifacts/SUMMARY.txt" 2>/dev/null
exit $code
