// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Shared identity utilities used by both the tool plane (axis_mcp_connector)
// and the inference plane (lemonade_proxy).
//
// Kept here so security-adjacent fallback logic — OS user resolution, hostname
// sanitisation, session-id minting — lives in exactly one place. Each plane
// passes its own env-var key list to resolveUser(); everything else is shared.

import { hostname, userInfo } from "node:os";
import { randomUUID } from "node:crypto";

/** Resolve the OS login username. Returns "" if the call fails or yields an
 *  empty value (some restricted containers, numeric UIDs, etc.) */
export function osUser() {
  try {
    const name = userInfo().username;
    return name && name.trim() ? name.trim() : "";
  } catch {
    return "";
  }
}

/** Safe hostname lookup — returns "localhost" on any failure. */
export function hostnameSafe() {
  try {
    return hostname();
  } catch {
    return "localhost";
  }
}

/** Mint or honour a session id.
 *  @param {string|undefined} envSession  injected id (trimmed)
 *  @param {string}           prefix      e.g. "cc" or "lp"
 */
export function makeSessionId(envSession, prefix) {
  if (envSession && envSession.trim()) return envSession.trim();
  return `${prefix}-${randomUUID()}`;
}

/** Resolve the acting user and WHERE it came from.
 *
 *  This is a deskside, single-machine, no-auth box. The honest principal is
 *  the OS user who launched the agent (machine login already authenticated the
 *  human). Resolution order — and its provenance:
 *    - `env`     an explicit value in one of `envVarKeys` (asserted by launcher)
 *    - `os`      the resolved OS login user (default on a deskside box)
 *    - `unknown` neither was resolvable
 *
 *  `user_source` keeps the telemetry honest and gives a clean upgrade path:
 *  when real auth arrives the launcher sets source="sso"; the field stays. */
export function resolveUser(envVarKeys, env = process.env) {
  for (const key of envVarKeys) {
    const val = (env[key] || "").trim();
    if (val) return { user: val, source: "env" };
  }
  const os = osUser();
  if (os) return { user: os, source: "os" };
  return { user: "unknown", source: "unknown" };
}
