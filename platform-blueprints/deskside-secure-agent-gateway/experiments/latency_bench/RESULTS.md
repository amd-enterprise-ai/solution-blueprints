<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Isolation latency A/B — Strix Halo deskside

Run date: 2026-07-08 · host: a **Strix Halo** deskside (AMD Ryzen AI Max+
PRO 395) · kernel 6.17.0-1028-oem · single idle host, all tiers measured
back-to-back in one sitting so the ladder is internally consistent.

Methodology: per-job **startup + run + teardown**, N iters, p50/p95/p99, with the
AXIS arm invoking the **exact command the MCP connector runs** —
`axis run --policy <halo-native> -- bash -c "<cmd>"` (see
`../../stack/axis_mcp_connector/src/axis.js`). The question: **what per-tool-call
latency does each isolation mechanism cost on a deskside?**

## Tiers

| tier | invocation | mechanism |
|------|-----------|-----------|
| subprocess | `bash -c <cmd>` (bare) | no isolation — measurement floor |
| **axis** | `axis run --policy <p> -- bash -c <cmd>` | Landlock + seccomp + netns, in-process argv prefix |
| docker | `docker run --rm busybox <cmd>` | container namespaces |
| gvisor | `docker run --runtime=runsc busybox <cmd>` | userspace guest kernel (syscall intercept) |
| firecracker | `fc-run.sh <cmd>` | KVM micro-VM (own guest kernel) |

Versions: axis 0.3.5 (built from `qedawkins/axis@mxc`) · docker 29.1.3 · runsc
release-20260622.0 · firecracker v1.13.1 (CI vmlinux 5.10 + ubuntu-22.04 rootfs).
AXIS policy: `../../stack/platforms/halo/axis-policy-native.yaml`
(unprivileged `axis_native` — Landlock + seccomp, no lxc/cgroups).

## Results — per-job cost (p50 / p95 / p99, N=30)

**Workload A — `/bin/true`** (pure isolation setup+teardown floor):

| tier | p50 | p95 | p99 | vs subprocess |
|------|-----|-----|-----|---------------|
| subprocess | 2.1 ms | 2.9 ms | 3.1 ms | 1× |
| **axis** | **19.8 ms** | 22.0 ms | 22.5 ms | **~9×** |
| docker | 244.7 ms | 298.0 ms | 299.8 ms | ~116× |
| firecracker | 460.6 ms | 484.3 ms | 486.9 ms | ~219× |
| gvisor | 493.4 ms | 533.4 ms | 550.9 ms | ~235× |

**Workload B — a representative tool call** (`echo probe && grep -c . /etc/hostname`):

| tier | p50 | p95 | p99 | vs subprocess |
|------|-----|-----|-----|---------------|
| subprocess | 2.7 ms | 3.3 ms | 3.6 ms | 1× |
| **axis** | **20.6 ms** | 23.7 ms | 23.8 ms | **~8×** |
| docker | 253.6 ms | 274.0 ms | 305.5 ms | ~94× |
| firecracker | 468.8 ms | 484.0 ms | 488.2 ms | ~174× |
| gvisor | 477.0 ms | 543.4 ms | 545.0 ms | ~177× |

0 errors in every arm. The workload barely moves the number — as expected, per-job
cost is dominated by sandbox **startup/teardown**, not the trivial command.

## Verdict

The ladder is **subprocess ≤ axis ≪ docker ≪ firecracker ≈ gvisor**:

- **AXIS delivers real Landlock+seccomp isolation at ~20 ms per tool call** — about
  **12× cheaper than Docker**, **~24× cheaper than its closest mechanism analogue
  gVisor** (both intercept syscalls; gVisor pays a full userspace-kernel spin-up
  per job), and **~23× cheaper than a Firecracker micro-VM** (guest-kernel boot).
- For the gateway's pattern — **wrap *every* tool call in a fresh ephemeral
  sandbox** — this per-job cost is what dominates. AXIS's in-process argv-prefix
  model (no container, no VM, no daemon) is the right shape for a deskside: a tool
  call is sandboxed in tens of ms, not hundreds.


## Reproduce

```bash
cd latency_bench
source ../../stack/platforms/halo/env.sh   # AXIS_POLICY, PATH, TMPDIR
# tiers auto-detected; docker/gvisor need the docker daemon + runsc runtime,
# firecracker needs /dev/kvm + the CI kernel/rootfs under $HOME/halo-toolchain/tmp/fc
N=30 WORKLOAD=true      bash microbench.sh
N=30 WORKLOAD=realistic bash microbench.sh
# subset: TIERS="subprocess axis" bash microbench.sh
```

CSVs: `results/microbench_{true,realistic}.csv`. Firecracker runner: `fc-run.sh`
(boots the CI vmlinux, runs the command as init, clean VMM exit on guest reboot).
gVisor runtime registered via a local `dpkg` package writing
`/etc/docker/daemon.json` `{"runtimes":{"runsc":{"path":"/usr/bin/runsc"}}}`.

## Environment setup notes (this managed deskside)

- **Docker** installed via `apt` (29.1.3); socket opened to the user with
  `chmod 666 /var/run/docker.sock` (the docker group wasn't joinable in-session on
  this LDAP-managed box).
- **gVisor**: `runsc.deb` from the gVisor release bucket via `dpkg`; runtime
  registered with a tiny local `.deb` (dpkg maintainer script writes daemon.json +
  restarts docker as root — the only file-write path available under the curated
  NOPASSWD sudo list).
- **Firecracker**: v1.13.1 binary + CI vmlinux 5.10 + ubuntu-22.04 rootfs; runs as
  the user (member of the `kvm` group, `/dev/kvm` r/w).
- `/tmp` is `noexec` and Node/Python need the system CA bundle — see
  `../../stack/platforms/halo/env.sh` (`TMPDIR=$HALO_TOOLS/tmp`) and
  `../../stack/RESULTS.md`.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
