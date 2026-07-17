// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// GPU consumption sampling for LOCAL inference.
//
// When a completion is served on the local tier (Lemonade on the Strix Halo
// APU), we attach a `gpu` block to the llm.request event so infra/O11y
// view can see device utilization, memory, power and energy for that call.
//
// This reads the amdgpu **sysfs** interface directly
// (/sys/class/drm/cardN/device/...), which is world-readable and needs neither
// ROCm nor root — important because the deskside boxes don't ship rocm-smi. If
// nothing is readable (no AMD GPU, a different driver, a locked-down sysfs), every
// function fails soft to null so inference telemetry is never broken by a missing
// counter. Values are normalized to human units (W, °C, MHz, bytes).
//
// Energy for a call is estimated as avg_power_W * duration_s: sample power at the
// start and end of the request and average (a coarse but useful Tokenomics signal
// for "estimated local cost" — real rate-card/energy modeling is downstream).

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const AMD_VENDOR = "0x1002";

/** Read a sysfs scalar file, trimmed. Returns null on any error. */
function readScalar(path) {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return null;
  }
}

function readInt(path) {
  const s = readScalar(path);
  if (s == null) return null;
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : null;
}

/** Locate the amdgpu card device dir. Honors GPU_SYSFS_PATH (used by tests and to
 *  pin a specific card); otherwise scans /sys/class/drm/cardN/device and picks the
 *  first whose vendor is AMD. Returns null when no AMD GPU is present. */
export function findGpuDevice(env = process.env, drmRoot = "/sys/class/drm") {
  const override = (env.GPU_SYSFS_PATH || "").trim();
  if (override) return override;
  let entries;
  try {
    entries = readdirSync(drmRoot);
  } catch {
    return null;
  }
  // Match cardN (a real card), NOT cardN-DP-1 (display connectors have no vendor).
  const cards = entries.filter((e) => /^card\d+$/.test(e)).sort();
  for (const c of cards) {
    const dev = join(drmRoot, c, "device");
    if (readScalar(join(dev, "vendor")) === AMD_VENDOR) return dev;
  }
  return null;
}

/** Find the amdgpu hwmon subdir (power/temp/freq live under
 *  <device>/hwmon/hwmonN/). Returns null if absent. */
function findHwmon(devDir) {
  const hwmonRoot = join(devDir, "hwmon");
  let entries;
  try {
    entries = readdirSync(hwmonRoot);
  } catch {
    return null;
  }
  const dirs = entries.filter((e) => /^hwmon\d+$/.test(e)).sort();
  // Prefer the one named "amdgpu"; fall back to the first.
  for (const d of dirs) {
    if (readScalar(join(hwmonRoot, d, "name")) === "amdgpu") return join(hwmonRoot, d);
  }
  return dirs.length ? join(hwmonRoot, dirs[0]) : null;
}

/** Take a one-shot sample of the AMD GPU. Returns null when no GPU/telemetry is
 *  available. All fields are best-effort: any single unreadable counter is null
 *  rather than failing the whole sample. */
export function sampleGpu(env = process.env, drmRoot = "/sys/class/drm") {
  if ((env.GPU_TELEMETRY || "on").toLowerCase() === "off") return null;
  const dev = findGpuDevice(env, drmRoot);
  if (!dev) return null;

  const vramUsed = readInt(join(dev, "mem_info_vram_used"));
  const vramTotal = readInt(join(dev, "mem_info_vram_total"));
  const gttUsed = readInt(join(dev, "mem_info_gtt_used"));
  const gttTotal = readInt(join(dev, "mem_info_gtt_total"));

  const hwmon = findHwmon(dev);
  const powerUw = hwmon ? readInt(join(hwmon, "power1_average")) : null;
  const powerInputUw = hwmon ? readInt(join(hwmon, "power1_input")) : null;
  const tempMc = hwmon ? readInt(join(hwmon, "temp1_input")) : null;
  const freqHz = hwmon ? readInt(join(hwmon, "freq1_input")) : null;

  const powerW = powerUw != null ? powerUw / 1e6 : powerInputUw != null ? powerInputUw / 1e6 : null;

  return {
    device: dev,
    busy_percent: readInt(join(dev, "gpu_busy_percent")),
    vram_used_bytes: vramUsed,
    vram_total_bytes: vramTotal,
    gtt_used_bytes: gttUsed,
    gtt_total_bytes: gttTotal,
    power_w: powerW,
    temp_c: tempMc != null ? tempMc / 1000 : null,
    sclk_mhz: freqHz != null ? Math.round(freqHz / 1e6) : null,
  };
}

/** Combine a start + end sample into a per-request GPU block, adding a coarse
 *  energy estimate (avg power * duration). Either sample may be null; the block is
 *  null only when both are. */
export function gpuBlock(startSample, endSample, durationMs) {
  const end = endSample || startSample;
  const start = startSample || endSample;
  if (!end) return null;

  const powers = [start?.power_w, end?.power_w].filter((p) => typeof p === "number");
  const powerAvgW = powers.length ? powers.reduce((a, b) => a + b, 0) / powers.length : null;
  const durationS = typeof durationMs === "number" ? durationMs / 1000 : null;
  const energyJoules =
    powerAvgW != null && durationS != null ? Math.round(powerAvgW * durationS * 1000) / 1000 : null;

  const busies = [start?.busy_percent, end?.busy_percent].filter((b) => typeof b === "number");
  const busyAvg = busies.length ? Math.round(busies.reduce((a, b) => a + b, 0) / busies.length) : null;

  return {
    busy_percent: end.busy_percent,
    busy_percent_avg: busyAvg,
    vram_used_bytes: end.vram_used_bytes,
    vram_total_bytes: end.vram_total_bytes,
    gtt_used_bytes: end.gtt_used_bytes,
    gtt_total_bytes: end.gtt_total_bytes,
    power_w: end.power_w,
    power_avg_w: powerAvgW != null ? Math.round(powerAvgW * 1000) / 1000 : null,
    energy_joules: energyJoules,
    temp_c: end.temp_c,
    sclk_mhz: end.sclk_mhz,
  };
}
