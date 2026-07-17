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
| Audit | **fail-closed** (`AUDIT_REQUIRED=1`) by default — a tool call is refused if the audit sink is unreachable |
| Toolchain | Go/Rust/AXIS/DefenseClaw built into `$HALO_TOOLS`, not committed |

## 0. Prerequisites (fresh Halo node)

`platforms/halo/setup.sh` builds Go, Rust, AXIS and DefenseClaw for you. You only need
these on the box first:

| Need | Why | Check |
|------|-----|-------|
| outbound internet | clone repos, download Go/Rust | `curl -sI https://github.com` |
| Node ≥18 (via nvm) | connector + probe; `setup.sh` does **not** install it | `node --version` |
| `git`, `curl`, `python3` | clone/build + bundled fake HEC | `git --version` |

No `sudo`, no privileged sandbox: everything installs under `$HALO_TOOLS` and the
policy is the unprivileged `platforms/halo/axis-policy-native.yaml`.

## 1. Reproduce from scratch

```bash
cd deskside-secure-agent-gateway/stack

# a. deskside environment (native policy, ports, hardening). Self-locating.
source platforms/halo/env.sh

# b. one-time toolchain build: Go, Rust, AXIS + DefenseClaw from source, npm deps,
#    unit tests, AXIS smoke test. Idempotent; installs into $HALO_TOOLS.
bash platforms/halo/setup.sh

# c. functional loop (both planes). Baseline expects 15/0 in artifacts/SUMMARY.txt.
bash platforms/halo/run.sh
RUN_CC=1 bash platforms/halo/run.sh          # + best-effort Claude-Code-via-Lemonade stage
```

Steps a–c share one shell: `source platforms/halo/env.sh` once, then everything below
inherits `HALO_TOOLS`, PATH, `AXIS_POLICY` and the hardening flags.

## 2. Run the red-team suite

The red-team runner is self-contained — it brings up its **own** stack (fake HEC
+ DefenseClaw + connector on dedicated ports) reusing the binaries `setup.sh`
built, so it does not collide with a functional run. Just make sure
`platforms/halo/env.sh` is sourced in the shell:

```bash
source platforms/halo/env.sh                            # if not already sourced above

REDTEAM_MODE=regression bash run_redteam.sh   # gate: exits non-zero on ANY breach
REDTEAM_MODE=discovery  bash run_redteam.sh   # never fails; use when adding probes
```

- **regression** is the one to run for validation — exit `0` means every attack
  was contained (blocked at DefenseClaw *or* the AXIS sandbox, and audited).
- Results: per-probe verdicts in `artifacts/redteam/` (`findings_table.md`,
  `events.jsonl`, `rt*.out`); the curated write-up is
  [`REDTEAM_FINDINGS.md`](./REDTEAM_FINDINGS.md).

## Notes

- **`$HALO_TOOLS`** holds the built binaries — override it to install elsewhere.
  The repo only ships config + wrappers, never binaries.
- **Ports**: `platforms/halo/env.sh` sets DefenseClaw `18970`, HEC `18088`, proxy `13399`;
  if a sibling test (e.g. a real Splunk on `18088`) is running, override
  `HEC_PORT`/`DC_PORT`/`PROXY_PORT`. The red-team uses its own dedicated ports.
- **Results**: [`RESULTS.md`](./RESULTS.md) (functional) and
  [`REDTEAM_FINDINGS.md`](./REDTEAM_FINDINGS.md) (adversarial).

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
