#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# fc-run.sh — boot a Firecracker microVM, run one command, tear it down.
#
# It times the SAME per-job shape as every other tier in microbench.sh: full
# guest-kernel boot + run(<cmd>) + shutdown. Firecracker is a KVM micro-VM (its
# own kernel), so this is the heaviest real isolation tier.
#
# Mechanism: Firecracker boots the CI vmlinux with the command injected via the
# kernel boot args as `init=`. A tiny init shim runs the command then triggers an
# immediate reboot (Firecracker maps the guest reboot to a clean VMM exit), so the
# process lifetime == boot+run+teardown. No API socket / long-lived VM needed.
#
# Env:
#   FC_BIN      firecracker binary       (default: $FC_DIR/firecracker)
#   FC_KERNEL   uncompressed vmlinux     (default: $FC_DIR/vmlinux)
#   FC_ROOTFS   ext4 rootfs image        (default: $FC_DIR/rootfs.ext4)
#   FC_CMD      command to run in guest  (default: /bin/true)
#   HALO_TOOLS  toolchain root           (default: $HOME/halo-toolchain; override to relocate)
# Needs: read/write /dev/kvm (this user is in the kvm group).
set -uo pipefail

HALO_TOOLS="${HALO_TOOLS:-$HOME/halo-toolchain}"
FCDIR="${FCDIR:-$HALO_TOOLS/tmp/fc}"
FC_BIN="${FC_BIN:-$FCDIR/firecracker}"
FC_KERNEL="${FC_KERNEL:-$FCDIR/vmlinux}"
FC_ROOTFS="${FC_ROOTFS:-$FCDIR/rootfs.ext4}"
FC_CMD="${FC_CMD:-/bin/true}"

work="$(mktemp -d "${TMPDIR:-/tmp}/fcrun.XXXXXX")"
sock="$work/fc.sock"
# Per-run overlay so the shared rootfs is never mutated and runs don't serialize
# on a single writable image. qemu-img not required: use a copy-on-nothing approach
# by giving Firecracker a fresh read-only rootfs + a scratch drive is overkill for
# /bin/true; we boot the rootfs read-only (ro) and run the command from it.
cleanup(){ rm -rf "$work" 2>/dev/null; }
trap cleanup EXIT

# Boot args: override init to /bin/sh so our command runs as PID 1, then
# `reboot -f` triggers a clean VMM exit (Firecracker maps guest reboot to exit,
# so process lifetime == boot+run+teardown). The kernel forwards everything after
# `--` to init; we pass `-c "<cmd>; reboot -f"` in DOUBLE quotes (single quotes
# get mangled through the boot_args string and panic the kernel on init exit).
# panic=-1 reboots immediately on any init fault as a safety net.
BOOTARGS="console=ttyS0 reboot=k panic=-1 pci=off i8042.noaux i8042.nomux i8042.nopnp i8042.dumbkbd ro init=/bin/sh -- -c \"${FC_CMD}; reboot -f\""

# Build the config with Python's json so the double quotes inside boot_args are
# escaped correctly (a hand-written heredoc produces invalid JSON here).
cfg="$work/config.json"
FC_KERNEL="$FC_KERNEL" FC_ROOTFS="$FC_ROOTFS" BOOTARGS="$BOOTARGS" python3 - "$cfg" <<'PY'
import json, os, sys
cfg = {
    "boot-source": {
        "kernel_image_path": os.environ["FC_KERNEL"],
        "boot_args": os.environ["BOOTARGS"],
    },
    "drives": [{
        "drive_id": "rootfs",
        "path_on_host": os.environ["FC_ROOTFS"],
        "is_root_device": True,
        "is_read_only": True,
    }],
    "machine-config": {"vcpu_count": 1, "mem_size_mib": 128},
}
with open(sys.argv[1], "w") as f:
    json.dump(cfg, f)
PY

# --no-api + --config-file boots straight from the JSON and exits when the guest
# halts/reboots — exactly the per-job lifetime we want to time.
"$FC_BIN" --no-api --config-file "$cfg" --no-seccomp >/dev/null 2>&1
