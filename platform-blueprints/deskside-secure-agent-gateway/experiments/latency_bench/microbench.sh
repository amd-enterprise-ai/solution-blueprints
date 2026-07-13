#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# microbench.sh — per-tool-call isolation latency A/B for the CLIENT integration.
#
# Measures the full per-job cost the axis MCP connector actually pays per tool
# call: startup + run(<cmd>) + teardown, N iters per tier, reported as p50/p95/p99.
# The AXIS arm invokes the EXACT command the connector runs (see
# ../../stack/axis_mcp_connector/src/axis.js:
# `axis run --policy <p> -- bash -c "<cmd>"`), on the Strix Halo native policy.
#
# Tiers (all run locally on this deskside, no daemon/gateway/root needed for the
# first two):
#   subprocess  — bare `bash -c <cmd>`            (no isolation; the 1x floor)
#   axis        — `axis run --policy <p> -- bash -c <cmd>`  (Landlock+seccomp+netns)
#   docker      — `docker run --rm <img> <cmd>`   (container namespaces)
#   gvisor      — `docker run --runtime=runsc ...`(userspace guest kernel; syscall intercept)
#   firecracker — `fc-run.sh <cmd>`               (KVM micro-VM; own guest kernel)
#
# Why this ladder: subprocess is the honest floor; AXIS is what the connector uses;
# Docker is the isolation tier real agent platforms actually ship; gVisor is AXIS's
# closest mechanism analogue (both intercept syscalls, gVisor via a userspace
# kernel); Firecracker is a true micro-VM (heaviest, own kernel).
#
#
# Usage (from this folder, a top-level sibling of gateway):
#   source ../../stack/platforms/halo/env.sh   # AXIS_POLICY, PATH, TMPDIR
#   bash microbench.sh                 # N=30, cmd=/bin/true, all five tiers
#   N=50 WORKLOAD=realistic bash microbench.sh
#   TIERS="subprocess axis" bash microbench.sh   # skip docker/gvisor/firecracker
#
# Env:
#   N         iterations per tier            (default 30)
#   WARMUP    discarded warmup iters/tier    (default 3)
#   TIERS     space-separated tier list      (default "subprocess axis docker gvisor firecracker")
#   WORKLOAD  true | realistic               (default true)
#               true      -> /bin/true  (pure isolation setup/teardown floor)
#               realistic -> a small shell tool call (echo + grep over /etc/hostname)
#   AXIS_BIN, AXIS_POLICY   AXIS binary + policy (from stack/platforms/halo/env.sh)
#   IMG       docker image for the docker tier   (default busybox:latest)
#   OUT       CSV output path                (default results/microbench.csv)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${N:-30}"
WARMUP="${WARMUP:-3}"
TIERS="${TIERS:-subprocess axis docker gvisor firecracker}"
WORKLOAD="${WORKLOAD:-true}"
AXIS_BIN="${AXIS_BIN:-axis}"
AXIS_POLICY="${AXIS_POLICY:-/etc/axis/coding-agent.yaml}"
IMG="${IMG:-busybox:latest}"
OUT="${OUT:-$HERE/results/microbench.csv}"
mkdir -p "$(dirname "$OUT")"

# The command executed INSIDE each sandbox. `true` is the pure setup+teardown floor;
# `realistic` is a representative connector tool call (a couple of cheap ops).
case "$WORKLOAD" in
  true)      CMD="true" ;;
  realistic) CMD="echo probe && grep -c . /etc/hostname" ;;
  *) echo "unknown WORKLOAD=$WORKLOAD (use: true | realistic)" >&2; exit 2 ;;
esac

run_subprocess(){ bash -c "$CMD"; }
run_axis(){ "$AXIS_BIN" run --policy "$AXIS_POLICY" -- bash -c "$CMD"; }
run_docker(){ docker run --rm "$IMG" sh -c "$CMD"; }
run_gvisor(){ docker run --rm --runtime=runsc "$IMG" sh -c "$CMD"; }
run_firecracker(){ FC_CMD="$CMD" bash "$HERE/fc-run.sh"; }

# Is a tier runnable on this box? Unavailable tiers are skipped (with a note) so
# the harness degrades gracefully on a machine without docker/runsc/kvm.
tier_available(){
  case "$1" in
    subprocess) return 0 ;;
    axis)       command -v "$AXIS_BIN" >/dev/null 2>&1 ;;
    docker)     docker info >/dev/null 2>&1 ;;
    gvisor)     docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q runsc ;;
    firecracker) [ -r /dev/kvm ] && [ -w /dev/kvm ] && [ -x "${FCDIR:-${HALO_TOOLS:-$HOME/halo-toolchain}/tmp/fc}/firecracker" ] ;;
    *) return 1 ;;
  esac
}

# pctl <p>: read numbers on stdin, print the p-th percentile (nearest-rank).
pctl(){ sort -n | awk -v p="$1" '{a[NR]=$0} END{n=NR; if(n==0){print "NA";exit} k=int((n*p+99)/100); if(k<1)k=1; if(k>n)k=n; printf "%.1f", a[k]}'; }
mean(){ awk '{s+=$1;n++} END{if(n)printf "%.1f",s/n; else print "NA"}'; }

echo "# gateway latency A/B — $(date -u +%FT%TZ)"
echo "# host=$(hostname) workload=$WORKLOAD cmd=\"$CMD\" N=$N warmup=$WARMUP policy=$AXIS_POLICY"
printf 'tier,p50_ms,p95_ms,p99_ms,mean_ms,min_ms,max_ms,iters,errors\n' | tee "$OUT"

for tier in $TIERS; do
  if ! tier_available "$tier"; then
    echo "# skip $tier — not available on this host" >&2
    printf '%s,NA,NA,NA,NA,NA,NA,0,skipped\n' "$tier" | tee -a "$OUT"
    continue
  fi
  # Warmup (fills caches / pulls image / first-run landlock setup) — discarded.
  for _ in $(seq 1 "$WARMUP"); do run_"$tier" >/dev/null 2>&1; done

  samples=(); errors=0
  for _ in $(seq 1 "$N"); do
    t0=$(date +%s.%N)
    if run_"$tier" >/dev/null 2>&1; then :; else errors=$((errors+1)); fi
    t1=$(date +%s.%N)
    samples+=( "$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f",(b-a)*1000}')" )
  done

  series="$(printf '%s\n' "${samples[@]}")"
  p50=$(echo "$series" | pctl 50)
  p95=$(echo "$series" | pctl 95)
  p99=$(echo "$series" | pctl 99)
  mn=$(echo "$series" | mean)
  lo=$(echo "$series" | sort -n | head -1)
  hi=$(echo "$series" | sort -n | tail -1)
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$tier" "$p50" "$p95" "$p99" "$mn" "$lo" "$hi" "$N" "$errors" | tee -a "$OUT"
done

echo "# CSV written to $OUT" >&2
