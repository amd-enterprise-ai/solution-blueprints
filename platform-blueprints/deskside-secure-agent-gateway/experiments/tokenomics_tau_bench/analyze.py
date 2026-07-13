#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tokenomics A/B analysis for τ-bench.

Usage: analyze.py <events_A.jsonl> <events_B.jsonl>
                  <results_A_retail_dir> <results_A_airline_dir>
                  <results_B_retail_dir> <results_B_airline_dir>

Pricing: Opus 4.8 $5/1M in, $25/1M out. US electricity $0.17/kWh.
Local token counts estimated from char counts when Lemonade omits usage (~4 chars/token).
"""
import glob
import json
import os
import sys
from collections import Counter

OPUS_IN = float(os.environ.get("OPUS_IN_PER_1M", "5.0"))
OPUS_OUT = float(os.environ.get("OPUS_OUT_PER_1M", "25.0"))
US_KWH = float(os.environ.get("US_KWH_USD", "0.17"))


def load_events(path):
    events = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("event") == "llm.request":
                        events.append(e)
                except json.JSONDecodeError:
                    pass  # skip malformed JSONL lines
    except FileNotFoundError:
        print(f"warning: events file not found: {path}", file=sys.stderr)
    return events


def summarize_events(events):
    s = dict(
        calls_total=0,
        calls_local=0,
        calls_frontier=0,
        in_tok_local=0,
        out_tok_local=0,
        in_tok_frontier=0,
        out_tok_frontier=0,
        energy_joules=0.0,
        gpu_samples=[],
    )
    for e in events:
        tier = (e.get("routing") or {}).get("tier", "local")
        res = e.get("result") or {}
        req = e.get("request") or {}
        it = res.get("prompt_tokens") or round((req.get("prompt_chars") or 0) / 4)
        ot = res.get("completion_tokens") or round((res.get("completion_chars") or 0) / 4)
        s["calls_total"] += 1
        if tier == "frontier":
            s["calls_frontier"] += 1
            s["in_tok_frontier"] += it
            s["out_tok_frontier"] += ot
        else:
            s["calls_local"] += 1
            s["in_tok_local"] += it
            s["out_tok_local"] += ot
            gpu = e.get("gpu") or {}
            ej = gpu.get("energy_joules")
            if isinstance(ej, (int, float)):
                s["energy_joules"] += ej
            pw = gpu.get("power_avg_w")
            if isinstance(pw, (int, float)):
                s["gpu_samples"].append(pw)
    return s


def load_tau_results(dir_path):
    """Parse tau-bench result JSON files → list of {task_id, reward}."""
    results = []
    if not os.path.isdir(dir_path):
        return results
    for f in glob.glob(os.path.join(dir_path, "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
            # tau-bench writes a list of run dicts, each with task_id + reward
            runs = d if isinstance(d, list) else d.get("results", [])
            for r in runs:
                results.append(
                    {
                        "task_id": r.get("task_id", -1),
                        "reward": float(r.get("reward", 0)),
                    }
                )
        except (json.JSONDecodeError, OSError, ValueError) as err:
            print(f"[warn] skipping invalid tau result file {f}: {err}", file=sys.stderr)
    return results


def fmt(x):
    return f"${x:.4f}"


def report(name, s, retail_results, airline_results):
    fc = (s["in_tok_frontier"] / 1e6) * OPUS_IN + (s["out_tok_frontier"] / 1e6) * OPUS_OUT
    kwh = s["energy_joules"] / 3.6e6
    lc = kwh * US_KWH
    avg_pw = sum(s["gpu_samples"]) / len(s["gpu_samples"]) if s["gpu_samples"] else 0.0
    pct_local = (s["calls_local"] / s["calls_total"] * 100) if s["calls_total"] else 0

    all_results = retail_results + airline_results
    n_solved = sum(1 for r in all_results if r["reward"] >= 1.0)
    avg_reward = sum(r["reward"] for r in all_results) / len(all_results) if all_results else 0.0

    print(f"## Arm {name}")
    print(
        f"  LLM calls: {s['calls_total']}  (local={s['calls_local']} {pct_local:.0f}%, frontier={s['calls_frontier']})"
    )
    print(f"  Frontier tokens: in={s['in_tok_frontier']:,}  out={s['out_tok_frontier']:,}")
    print(f"  Local tokens (est): in={s['in_tok_local']:,}  out={s['out_tok_local']:,}")
    print(f"  Frontier cost (Opus 4.8 @ ${OPUS_IN}/${OPUS_OUT} per 1M): {fmt(fc)}")
    ej = s["energy_joules"]
    print(f"  Local energy: {ej:.1f} J = {kwh*1000:.3f} Wh (avg {avg_pw:.1f} W)  →  {fmt(lc)}")
    print(f"  Total cost (frontier + local energy): {fmt(fc+lc)}")
    print(f"  Task results: {len(all_results)} tasks, {n_solved} solved, avg reward {avg_reward:.3f}")
    r_retail = sum(r["reward"] for r in retail_results) / len(retail_results) if retail_results else 0
    r_airline = sum(r["reward"] for r in airline_results) / len(airline_results) if airline_results else 0
    print(f"    retail avg reward: {r_retail:.3f}  airline avg reward: {r_airline:.3f}")
    print()
    return {
        "frontier_cost": fc,
        "local_cost": lc,
        "total": fc + lc,
        "pct_local": pct_local,
        "avg_reward": avg_reward,
        **s,
    }


def main():
    a_events_path, b_events_path = sys.argv[1], sys.argv[2]
    a_retail_dir, a_airline_dir = sys.argv[3], sys.argv[4]
    b_retail_dir, b_airline_dir = sys.argv[5], sys.argv[6]

    sA = summarize_events(load_events(a_events_path))
    sB = summarize_events(load_events(b_events_path))

    print("# Tokenomics A/B — τ-bench (router-on vs frontier-only)")
    print(f"# Opus 4.8: ${OPUS_IN}/1M in, ${OPUS_OUT}/1M out  |  US electricity: ${US_KWH}/kWh\n")
    rA = report("A (router-on)", sA, load_tau_results(a_retail_dir), load_tau_results(a_airline_dir))
    rB = report("B (frontier-only)", sB, load_tau_results(b_retail_dir), load_tau_results(b_airline_dir))

    print("## Comparison (A vs B)")
    saved = rB["total"] - rA["total"]
    pct = (saved / rB["total"] * 100) if rB["total"] else 0
    print(f"  Frontier cost  A={fmt(rA['frontier_cost'])}  B={fmt(rB['frontier_cost'])}")
    print(f"  Local energy   A={fmt(rA['local_cost'])}  B={fmt(rB['local_cost'])}")
    print(f"  Total cost     A={fmt(rA['total'])}  B={fmt(rB['total'])}")
    print(f"  Net saving A vs B: {fmt(saved)} ({pct:.1f}%)")
    print(f"  Local offload A: {rA['calls_local']} / {rA['calls_total']} ({rA['pct_local']:.0f}%)")
    print(
        f"  Avg reward  A={rA['avg_reward']:.3f}  B={rB['avg_reward']:.3f}  "
        f"(delta {rA['avg_reward']-rB['avg_reward']:+.3f})"
    )


if __name__ == "__main__":
    main()
