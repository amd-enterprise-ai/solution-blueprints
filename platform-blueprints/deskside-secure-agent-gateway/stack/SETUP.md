<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# SETUP — running the deskside secure agent gateway on a Strix Halo deskside

Stands up both planes of the governance loop on a **Strix Halo** box — a single
**unprivileged** Ryzen AI Max+ 395 deskside (no lxc-exec, no `CAP_NET_ADMIN`, no
writable cgroups v2). Everything Halo-specific lives in [`platforms/halo/`](./platforms/halo/) so the
run is reproducible from the repo, not from a personal home directory.

## How the sandbox and audit are configured here

The unprivileged box shapes three choices, all baked into `platforms/halo/`:

| Aspect | Configuration on Halo |
|--------|-----------------------|
| AXIS backend | **`platforms/halo/axis-policy-native.yaml`** — `axis_native` (Landlock + seccomp + netns block); no privileged lxc-exec needed |
| Process limits | no writable cgroups → **userspace `ulimit -u`** cap (`AXIS_ULIMIT_NPROC`), sized above the live thread baseline |
| Audit | **fail-closed** (`AUDIT_REQUIRED=1`) by default — a tool call is refused if the SQLite audit DB is unwritable |
| Toolchain | Go/Rust/AXIS built into `$HALO_TOOLS`, not committed |

## 0. Prerequisites (fresh Halo node)

`platforms/halo/setup.sh` builds Go, Rust and AXIS for you. You only need
these on the box first:

| Need | Why | Check |
|------|-----|-------|
| outbound internet | clone repos, download Go/Rust | `curl -sI https://github.com` |
| Node ≥18 (via nvm) | connector + probe; `setup.sh` does **not** install it | `node --version` |
| `git`, `curl`, `python3` | clone/build | `git --version` |

No `sudo`, no privileged sandbox: everything installs under `$HALO_TOOLS` and the
policy is the unprivileged `platforms/halo/axis-policy-native.yaml`.

## 1. Reproduce from scratch

```bash
cd deskside-secure-agent-gateway/stack

# a. deskside environment (native policy, ports, hardening). Self-locating.
source platforms/halo/env.sh

# b. one-time toolchain build: Go, Rust, AXIS from source, npm deps,
#    unit tests, AXIS smoke test. Idempotent; installs into $HALO_TOOLS.
bash platforms/halo/setup.sh

# c. functional loop (both planes). Baseline expects 15/0 in artifacts/SUMMARY.txt.
bash platforms/halo/run.sh
RUN_CC=1 bash platforms/halo/run.sh          # + best-effort Claude-Code-via-Lemonade stage
```

Steps a–c share one shell: `source platforms/halo/env.sh` once, then everything below
inherits `HALO_TOOLS`, PATH, `AXIS_POLICY` and the hardening flags.

## Notes

- **`$HALO_TOOLS`** holds the built binaries — override it to install elsewhere.
  The repo only ships config + wrappers, never binaries.
- **Ports**: `platforms/halo/env.sh` sets the Lemonade upstream `13305` and proxy
  `13399`; override `LEMONADE_PORT`/`PROXY_PORT` if occupied on the shared box.
- **Results**: [`RESULTS.md`](./RESULTS.md).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
