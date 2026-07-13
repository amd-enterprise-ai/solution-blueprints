#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# query_splunk.sh — pull the AXIS governance events back out of a real Splunk via
# its REST search API, so a run can assert against what Splunk actually indexed
# (not just what we POSTed to HEC).
#
# Env:
#   SPLUNK_MGMT_URL    management/search API base   (default: https://127.0.0.1:8089)
#   SPLUNK_USER        Splunk user                  (default: admin)
#   SPLUNK_PASS        Splunk password              (required)
#   SPLUNK_INDEX       index to search              (default: axis)
#   EARLIEST           search window start          (default: -15m)
#
set -uo pipefail
MGMT="${SPLUNK_MGMT_URL:-https://127.0.0.1:8089}"
USER="${SPLUNK_USER:-admin}"
PASS="${SPLUNK_PASS:?SPLUNK_PASS required}"
INDEX="${SPLUNK_INDEX:-axis}"
EARLIEST="${EARLIEST:--15m}"

# `spath` parses the JSON `_raw` into fields (the custom sourcetype isn't wired
# for index-time JSON extraction, so we extract at search time). Nested keys
# surface with dotted names: command.argv_redacted, result.exit, identity.session.
SEARCH="search index=${INDEX} | spath | sort 0 _time | table _time event decision command.argv_redacted result.exit identity.session"

# Splunk's export endpoint streams one JSON object per line; -k for the
# self-signed cert. Capture to a temp file (NOT a pipe into `python3 - <<'PY'`:
# the heredoc would claim python's stdin and the piped results would be lost).
RESP="$(mktemp "${TMPDIR:-/tmp}/splunk_q.XXXXXX.jsonl")"
trap 'rm -f "$RESP"' EXIT
curl -sk -u "$USER:$PASS" "$MGMT/services/search/jobs/export" \
  --data-urlencode "search=$SEARCH" \
  --data-urlencode "earliest_time=$EARLIEST" \
  --data-urlencode "latest_time=now" \
  --data-urlencode "output_mode=json" \
  -o "$RESP"

python3 - "$RESP" <<'PY'
import json,sys
# spath + Splunk's automatic JSON KV extraction both fire, so a field can come
# back as a 2-element list of identical values; collapse to a scalar.
def one(v, default="-"):
    if isinstance(v, list): v = v[0] if v else default
    return default if v is None or v == "" else v
n=0
for line in open(sys.argv[1]):
    line=line.strip()
    if not line: continue
    try: obj=json.loads(line)
    except json.JSONDecodeError: continue
    r=obj.get("result")
    if not r: continue
    n+=1
    print(f"  {one(r.get('_time'),'')}  {str(one(r.get('event'),'')):20s} "
          f"decision={str(one(r.get('decision'))):8s} exit={one(r.get('result.exit'))} "
          f"argv={str(one(r.get('command.argv_redacted'),''))!r}")
print(f"\n  {n} events returned from Splunk index")
PY
