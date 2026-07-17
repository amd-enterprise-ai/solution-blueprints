#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Group a client-side telemetry capture into a per-turn trace view.

Reads newline-delimited audit events (both planes: axis.* tool-plane and llm.*
inference-plane) and renders a human-readable Markdown report where the top-level
grouping is the `trace_id` — one user prompt plus all the LLM calls and tool
calls it triggered until the next user prompt. One agent session
(identity.session) contains multiple traces (one per turn).

Usage: group_by_trace.py <events.ndjson>  > by_trace.md

Stdlib only.
"""
import json
import sys
from collections import defaultdict


def load(path):
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def short(x, n=12):
    return (x[:n] + "…") if isinstance(x, str) and len(x) > n else x


def fmt_llm(ev):
    r = ev.get("request", {})
    res = ev.get("result", {})
    attrs = ev.get("attributes", {})
    gpu = ev.get("gpu")
    parts = [
        f"span={short(ev.get('span_id'))}",
        f"model={r.get('model')}",
        f"provider={attrs.get('gen_ai.provider.name')}",
        f"loc={attrs.get('execution_location')}",
        f"in={res.get('prompt_tokens')} out={res.get('completion_tokens')}",
        f"{res.get('duration_ms')}ms",
        f"decision={ev.get('decision')}",
    ]
    line = "    - **llm.request** " + " ".join(str(p) for p in parts)
    if gpu:
        line += (
            f"\n      gpu: busy={gpu.get('busy_percent')}% "
            f"power={gpu.get('power_w')}W avg={gpu.get('power_avg_w')}W "
            f"energy={gpu.get('energy_joules')}J "
            f"vram_used={gpu.get('vram_used_bytes')}B "
            f"temp={gpu.get('temp_c')}C sclk={gpu.get('sclk_mhz')}MHz"
        )
    return line


def fmt_tool(ev):
    cmd = ev.get("command", {})
    res = ev.get("result", {})
    argv = cmd.get("argv_redacted") or []
    cmd_str = argv[-1] if argv else ""
    parts = [
        f"span={short(ev.get('span_id'))}",
        f"decision={ev.get('decision')}",
        f"exit={res.get('exit')}",
        f"{res.get('duration_ms')}ms",
    ]
    return "    - **axis.toolcall** " + " ".join(str(p) for p in parts) + f"\n      `{cmd_str}`"


def main():
    if len(sys.argv) < 2:
        print("usage: group_by_trace.py <events.ndjson>", file=sys.stderr)
        sys.exit(2)
    events = load(sys.argv[1])
    events.sort(key=lambda e: e.get("time", 0))

    sessions = defaultdict(list)
    for ev in events:
        sid = (ev.get("identity") or {}).get("session", "?")
        sessions[sid].append(ev)

    print("# Agent session — per-trace view\n")
    print(
        "Grouping: **session → trace (one user turn) → ordered LLM + tool calls**. "
        "Session-lifecycle events (`*.session_start`/`_end`) have no trace_id.\n"
    )

    for sid, evs in sessions.items():
        print(f"## session `{sid}`\n")
        # split lifecycle (no trace) from traced events
        traced = defaultdict(list)
        lifecycle = []
        for ev in evs:
            tid = ev.get("trace_id")
            if tid:
                traced[tid].append(ev)
            else:
                lifecycle.append(ev)

        if lifecycle:
            print("**session lifecycle:** " + ", ".join(f"`{ev.get('event')}`" for ev in lifecycle) + "\n")

        # order traces by their first event time
        order = sorted(traced.items(), key=lambda kv: min(e.get("time", 0) for e in kv[1]))
        for i, (tid, tevs) in enumerate(order):
            turn = next(
                (
                    e.get("attributes", {}).get("axis.turn")
                    for e in tevs
                    if e.get("attributes", {}).get("axis.turn") is not None
                ),
                i,
            )
            n_llm = sum(1 for e in tevs if e.get("event") == "llm.request")
            n_tool = sum(1 for e in tevs if e.get("event") == "axis.toolcall")
            print(f"### trace `{tid}`  (turn {turn} — {n_llm} LLM call(s), {n_tool} tool call(s))\n")
            for ev in sorted(tevs, key=lambda e: e.get("time", 0)):
                et = ev.get("event")
                if et == "llm.request":
                    print(fmt_llm(ev))
                elif et == "axis.toolcall":
                    print(fmt_tool(ev))
            print()

    # summary
    all_traces = {ev.get("trace_id") for ev in events if ev.get("trace_id")}
    print("---\n")
    print(f"**Totals:** {len(events)} events, {len(sessions)} session(s), " f"{len(all_traces)} distinct trace_id(s).")


if __name__ == "__main__":
    main()
