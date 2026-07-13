<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# latency_bench — isolation latency A/B

Per-tool-call isolation overhead for the gateway
([`../../stack/`](../../stack/)), measured on a real Strix Halo deskside.
Answers: *what does each sandbox mechanism cost per tool call?*

Tiers: **subprocess** (floor) · **axis** (Landlock+seccomp, what the connector
actually uses) · **docker** · **gvisor** (runsc) · **firecracker** (KVM micro-VM).
Each is timed as full startup + run + teardown, N iters, p50/p95/p99.

## Run

```bash
cd latency_bench
source ../../stack/platforms/halo/env.sh   # AXIS_POLICY, PATH, TMPDIR
N=30 WORKLOAD=true      bash microbench.sh   # /bin/true floor
N=30 WORKLOAD=realistic bash microbench.sh   # a real tool call
TIERS="subprocess axis" bash microbench.sh   # subset (no docker/vm)
```

Env knobs: `N`, `WARMUP`, `TIERS`, `WORKLOAD` (`true`|`realistic`), `IMG`,
`AXIS_BIN`, `AXIS_POLICY`, `OUT`. See the header of `microbench.sh`.

## Files

- `microbench.sh` — the A/B harness.
- `fc-run.sh` — Firecracker per-job runner (boots CI vmlinux, runs the command as
  init, clean VMM exit on guest reboot). Needs `/dev/kvm` + kernel/rootfs under
  `$HOME/halo-toolchain/tmp/fc`.
- `results/` — CSV output (git-ignored).
- [`RESULTS.md`](./RESULTS.md) — the verified run + verdict.

## Prerequisites per tier

| tier | needs |
|------|-------|
| subprocess, axis | nothing beyond the built `axis` on PATH |
| docker, gvisor | docker daemon + `runsc` runtime registered in `/etc/docker/daemon.json` |
| firecracker | `/dev/kvm` (user in `kvm` group) + `fc/{firecracker,vmlinux,rootfs.ext4}` |

Setup specifics for this deskside are in `RESULTS.md` § "Environment setup notes".

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
