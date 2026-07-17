#!/bin/bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Deterministic grader (SOFT / reported — never gates the integration run).
# Applies the instance's official test_patch onto the repo the model edited, then
# runs the FAIL_TO_PASS test. SOLVED=yes iff it passes. The model's source edit
# (if any) is whatever it left in the working tree; we only add the official test.
#
# Args: $1 = repo workdir, $2 = instance.json, $3 = python bin (venv), $4 = out dir
set -uo pipefail

TASKDIR="${1:?repo workdir required}"
INSTANCE="${2:?instance.json required}"
PY="${3:-python3}"
OUT="${4:-.}"
mkdir -p "$OUT"

# Extract test_patch + the FAIL_TO_PASS node ids (no jq dependency).
"$PY" - "$INSTANCE" "$OUT/test.patch" "$OUT/f2p.txt" <<'PY'
import json, sys
inst = json.load(open(sys.argv[1]))
open(sys.argv[2], "w").write(inst["test_patch"])
open(sys.argv[3], "w").write("\n".join(inst["FAIL_TO_PASS"]))
PY

mapfile -t F2P < "$OUT/f2p.txt"
cd "$TASKDIR" || { echo "SOLVED=no"; exit 0; }

# Apply the official test (idempotent: skip if already applied).
if git apply --check "$OUT/test.patch" 2>/dev/null; then
  git apply --whitespace=nowarn "$OUT/test.patch"
  echo "[grade] applied test_patch"
elif git apply --reverse --check "$OUT/test.patch" 2>/dev/null; then
  echo "[grade] test_patch already applied"
else
  echo "[grade] WARNING: test_patch did not apply cleanly; grading on current tree"
fi

echo "[grade] running FAIL_TO_PASS: ${F2P[*]}"
"$PY" -m pytest -q -p no:cacheprovider "${F2P[@]}" > "$OUT/grade_pytest.txt" 2>&1
RC=$?
tail -20 "$OUT/grade_pytest.txt"

if [ "$RC" -eq 0 ]; then
  echo "SOLVED=yes"
else
  echo "SOLVED=no"
fi
exit 0
