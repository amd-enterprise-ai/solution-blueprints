// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { findGpuDevice, sampleGpu, gpuBlock } from "../src/gpu.js";

// Build a fake /sys/class/drm tree so the sysfs reader is testable without a GPU.
async function makeDrmFixture({ vendor = "0x1002", withHwmon = true } = {}) {
  const root = await mkdtemp(join(tmpdir(), "drm-"));
  // A display connector (no vendor) that must be ignored, and a real card.
  await mkdir(join(root, "card0-DP-1", "device"), { recursive: true });
  const dev = join(root, "card0", "device");
  await mkdir(dev, { recursive: true });
  await writeFile(join(dev, "vendor"), vendor + "\n");
  await writeFile(join(dev, "gpu_busy_percent"), "42\n");
  await writeFile(join(dev, "mem_info_vram_used"), "1855008768\n");
  await writeFile(join(dev, "mem_info_vram_total"), "34359738368\n");
  await writeFile(join(dev, "mem_info_gtt_used"), "193708032\n");
  await writeFile(join(dev, "mem_info_gtt_total"), "50500648960\n");
  if (withHwmon) {
    const hw = join(dev, "hwmon", "hwmon7");
    await mkdir(hw, { recursive: true });
    await writeFile(join(hw, "name"), "amdgpu\n");
    await writeFile(join(hw, "power1_average"), "14068000\n"); // µW -> 14.068 W
    await writeFile(join(hw, "power1_input"), "14100000\n");
    await writeFile(join(hw, "temp1_input"), "37000\n"); // m°C -> 37 °C
    await writeFile(join(hw, "freq1_input"), "625000000\n"); // Hz -> 625 MHz
  }
  return root;
}

test("findGpuDevice picks the AMD card, ignoring display connectors", async () => {
  const root = await makeDrmFixture();
  try {
    const dev = findGpuDevice({}, root);
    assert.ok(dev.endsWith("/card0/device"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("findGpuDevice returns null when no AMD vendor is present", async () => {
  const root = await makeDrmFixture({ vendor: "0x10de" }); // nvidia
  try {
    assert.equal(findGpuDevice({}, root), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("GPU_SYSFS_PATH override wins", () => {
  assert.equal(findGpuDevice({ GPU_SYSFS_PATH: "/x/y" }), "/x/y");
});

test("sampleGpu normalizes sysfs units (W, °C, MHz)", async () => {
  const root = await makeDrmFixture();
  try {
    const s = sampleGpu({}, root);
    assert.equal(s.busy_percent, 42);
    assert.equal(s.vram_used_bytes, 1855008768);
    assert.equal(s.vram_total_bytes, 34359738368);
    assert.equal(s.power_w, 14.068);
    assert.equal(s.temp_c, 37);
    assert.equal(s.sclk_mhz, 625);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("sampleGpu returns null when GPU_TELEMETRY=off", async () => {
  const root = await makeDrmFixture();
  try {
    assert.equal(sampleGpu({ GPU_TELEMETRY: "off" }, root), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("sampleGpu tolerates a missing hwmon (power/temp null, mem still read)", async () => {
  const root = await makeDrmFixture({ withHwmon: false });
  try {
    const s = sampleGpu({}, root);
    assert.equal(s.busy_percent, 42);
    assert.equal(s.vram_used_bytes, 1855008768);
    assert.equal(s.power_w, null);
    assert.equal(s.temp_c, null);
    assert.equal(s.sclk_mhz, null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("sampleGpu returns null when no GPU device exists", async () => {
  const root = await mkdtemp(join(tmpdir(), "empty-drm-"));
  try {
    assert.equal(sampleGpu({}, root), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("gpuBlock estimates energy as avg_power * duration", () => {
  const start = { busy_percent: 10, power_w: 10, vram_used_bytes: 1, vram_total_bytes: 2, gtt_used_bytes: 3, gtt_total_bytes: 4, temp_c: 30, sclk_mhz: 600 };
  const end = { busy_percent: 90, power_w: 30, vram_used_bytes: 5, vram_total_bytes: 2, gtt_used_bytes: 6, gtt_total_bytes: 4, temp_c: 50, sclk_mhz: 2900 };
  const b = gpuBlock(start, end, 2000); // 2s, avg power (10+30)/2 = 20 W -> 40 J
  assert.equal(b.power_avg_w, 20);
  assert.equal(b.energy_joules, 40);
  assert.equal(b.busy_percent, 90); // end value
  assert.equal(b.busy_percent_avg, 50);
  assert.equal(b.vram_used_bytes, 5); // end value
});

test("gpuBlock returns null when both samples are null", () => {
  assert.equal(gpuBlock(null, null, 1000), null);
});

test("gpuBlock works with only one sample (no energy without power pair still ok)", () => {
  const one = { busy_percent: 50, power_w: 12, vram_used_bytes: 1, vram_total_bytes: 2, gtt_used_bytes: 3, gtt_total_bytes: 4, temp_c: 40, sclk_mhz: 700 };
  const b = gpuBlock(one, null, 1000);
  assert.equal(b.power_w, 12);
  assert.equal(b.power_avg_w, 12);
  assert.equal(b.energy_joules, 12); // 12 W * 1 s
});
