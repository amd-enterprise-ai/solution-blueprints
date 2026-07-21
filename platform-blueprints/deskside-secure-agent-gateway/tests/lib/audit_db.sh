# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Shared audit-DB helpers for the integration test scripts.
#
# Source this after setting AUDIT_DB:
#   AUDIT_DB="$ART/audit.db"
#   source "<repo>/tests/lib/audit_db.sh"
#
# Why these exist: the naive check `query_db | grep X | grep -q Y` SIGPIPEs the
# upstream `query_db` (python) once its output exceeds the ~64KB pipe buffer,
# because `grep -q` exits on first match and closes the pipe. Under
# `set -o pipefail` that 141 exit propagates and the check spuriously FAILS on
# exactly the large-DB runs that matter. Every helper below captures query_db
# output into a variable FIRST, then filters — no mid-pipeline `grep -q`.

# Print every event row (one JSON object per line) from the audit DB.
query_db() {
  AUDIT_DB="$AUDIT_DB" python3 - <<'PY' 2>/dev/null
import os, sqlite3
try:
  db = sqlite3.connect(os.environ.get('AUDIT_DB', ''))
  for (data,) in db.execute('SELECT data FROM events ORDER BY id'):
    print(data)
except Exception:
  pass
PY
}

# True if at least one audit-DB line matches ALL given fixed-strings (grep -F).
# SIGPIPE-safe: captures into a variable, no mid-pipeline grep -q.
db_has() { # pat1 [pat2 ...]
  local out; out="$(query_db)"
  local p
  for p in "$@"; do out="$(printf '%s\n' "$out" | grep -F "$p" || true)"; done
  [ -n "$out" ]
}

# Poll (up to ~30s) until at least one audit-DB line matches ALL given
# fixed-strings. Use when the writer flushes asynchronously.
db_wait_line() { # pat1 [pat2 ...]
  local i
  for i in $(seq 1 30); do
    db_has "$@" && return 0
    sleep 1
  done
  return 1
}

# Backward-compatible single-pattern poll (count-based; grep -c drains the pipe
# so it is not SIGPIPE-vulnerable). Kept for callers that just wait on presence.
db_wait() { # pattern min_count
  local pat="$1" cnt="$2" found
  for _ in $(seq 1 30); do
    found="$(query_db | grep -c "$pat" || true)"
    [ "${found:-0}" -ge "$cnt" ] && return 0
    sleep 1
  done
  return 1
}
