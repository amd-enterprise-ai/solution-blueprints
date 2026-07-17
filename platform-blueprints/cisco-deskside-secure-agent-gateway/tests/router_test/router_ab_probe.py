#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""router_test A/B probe — per-prompt routing through the proxy.

There is no orchestrator and no rack control plane — everything runs on one
machine. The PROXY owns the toggle (LEMON_ROUTER=on|off) and CONSULTS the
semantic router per prompt. So this probe never sends "auto" — it always sends the
same Anthropic /v1/messages request (local model id) and lets the proxy decide.
The routing decision is read back from the proxy's additive x-lemon-* RESPONSE
headers (the proxy never alters the body).

For each prompt the probe:
  1. POSTs /v1/messages to the proxy base URL (baseline proxy = router off,
     router-on proxy = router on);
  2. reads x-lemon-router / x-lemon-tier / x-lemon-selected-model /
     x-lemon-complexity from the response headers;
  3. records latency, Anthropic token usage, and a per-tier cost estimate.

It runs the two toggle positions (against the two proxy URLs the runner starts)
back to back and prints a per-prompt table plus routing correctness and the cost /
latency A/B deltas. No secrets here: the frontier key lives only in the proxy env.

Pure helpers (tier/cost/header parsing, expectation) are import-safe and free of
network I/O so test_router_ab_probe.py can unit-test them.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# Per-1M-token prices (USD). Local Lemonade is free; the frontier tier is priced
# at published Claude Opus rates so the A/B cost delta is meaningful.
PRICING = {
    "local": {"prompt": 0.0, "completion": 0.0},
    "frontier": {"prompt": 15.0, "completion": 75.0},
}

# The model id the client sends on every request (the local Lemonade model). In
# router-on mode the proxy rewrites this to the frontier model when it escalates;
# the client body itself is identical in both A/B passes.
LOCAL_MODEL = "lemonade-local"


def model_tier(model: str) -> str:
    """Map a model NAME to its routing tier ('frontier' or 'local')."""
    return "frontier" if (model or "").startswith("claude-") else "local"


@dataclass
class Prompt:
    text: str
    # "simple" -> expected local route; "reasoning" -> expected frontier route.
    expected_domain: str


# A 7-prompt stream (4 simple, 3 reasoning).
DEFAULT_PROMPTS: list[Prompt] = [
    Prompt("What is the capital of France?", "simple"),
    Prompt("Convert 100 degrees Fahrenheit to Celsius.", "simple"),
    Prompt("What year did the Apollo 11 mission land on the Moon?", "simple"),
    Prompt("Define the word 'photosynthesis' in one sentence.", "simple"),
    Prompt(
        "Prove that the square root of 2 is irrational, showing every step of " "the contradiction argument.",
        "reasoning",
    ),
    Prompt(
        "Design an algorithm to find the median of two sorted arrays in "
        "O(log(m+n)) time and explain why it is correct.",
        "reasoning",
    ),
    Prompt(
        "A farmer must cross a river with a wolf, a goat, and a cabbage using a "
        "boat that holds only one item. Plan the full sequence of crossings and "
        "justify why nothing gets eaten.",
        "reasoning",
    ),
]


def cost_usd(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Cost of one call in USD from token counts. Unknown tiers are free."""
    p = PRICING.get(tier, {"prompt": 0.0, "completion": 0.0})
    return prompt_tokens / 1_000_000 * p["prompt"] + completion_tokens / 1_000_000 * p["completion"]


def expected_tier(domain: str) -> str:
    """Which tier SHOULD serve a domain, when routing is on."""
    return "frontier" if domain == "reasoning" else "local"


def routing_from_headers(headers: dict[str, str]) -> dict[str, str | None]:
    """Pull the proxy's additive routing headers, case-insensitively.
    Returns {router, tier, selected_model, complexity} (values None if absent)."""
    lower = {k.lower(): v for k, v in headers.items()}
    return {
        "router": lower.get("x-lemon-router"),
        "tier": lower.get("x-lemon-tier"),
        "selected_model": lower.get("x-lemon-selected-model"),
        "complexity": lower.get("x-lemon-complexity"),
    }


@dataclass
class CallResult:
    prompt: Prompt
    proxy_url: str
    router_on: bool
    tier: str | None
    selected_model: str | None
    complexity: str | None
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    cost: float
    ok: bool
    status: int = 0
    error: str | None = None

    @property
    def served_tier(self) -> str:
        """The tier that actually served — the header tier, defaulting local.
        When the router picks frontier but no frontier key is configured, the
        proxy fails safe and serves local, so this reads 'local'."""
        return self.tier or "local"

    @property
    def decision_tier(self) -> str:
        """The tier the ROUTER decided on, independent of whether the proxy could
        honor it. Derived from the router's recommended model (x-lemon-selected-
        model); falls back to the served tier when no model was reported. This
        proves the classification even when no frontier key is present."""
        if self.selected_model:
            return model_tier(self.selected_model)
        return self.served_tier


def _http_messages(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": "dummy",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
        hdrs = {k: v for k, v in resp.headers.items()}
        return resp.status, body, hdrs


def _usage_tokens(body: dict) -> tuple[int, int]:
    """Parse usage from Anthropic /v1/messages or OpenAI /v1/chat/completions."""
    usage = body.get("usage", {}) or {}
    # Anthropic: input_tokens / output_tokens; OpenAI: prompt_tokens / completion_tokens
    pt = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
    ct = int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
    return pt, ct


def run_one(
    prompt: Prompt,
    proxy_url: str,
    router_on: bool,
    timeout: float,
    max_tokens: int,
    model: str = LOCAL_MODEL,
) -> CallResult:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt.text}],
    }
    t0 = time.time()
    try:
        status, body, hdrs = _http_messages(f"{proxy_url.rstrip('/')}/v1/chat/completions", payload, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return CallResult(
            prompt,
            proxy_url,
            router_on,
            None,
            None,
            None,
            time.time() - t0,
            0,
            0,
            0.0,
            ok=False,
            error=str(e),
        )
    latency = time.time() - t0
    r = routing_from_headers(hdrs)
    pt, ct = _usage_tokens(body)
    tier = r["tier"] or "local"
    return CallResult(
        prompt,
        proxy_url,
        router_on,
        tier,
        r["selected_model"],
        r["complexity"],
        latency,
        pt,
        ct,
        cost_usd(tier, pt, ct),
        ok=(status < 400),
        status=status,
    )


@dataclass
class Summary:
    label: str
    results: list[CallResult] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.results if r.ok)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def avg_latency(self) -> float:
        oks = [r.latency_s for r in self.results if r.ok]
        return sum(oks) / len(oks) if oks else 0.0

    @property
    def cost_per_task(self) -> float:
        return self.total_cost / self.ok_count if self.ok_count else 0.0


def print_table(summary: Summary) -> None:
    print(f"\n=== {summary.label} ===")
    print(f"{'prompt':<40} {'exp':<9} {'tier':<9} {'selected':<18} {'cplx':<12} {'lat_s':>6} {'cost$':>10}")
    for r in summary.results:
        text = (r.prompt.text[:37] + "...") if len(r.prompt.text) > 40 else r.prompt.text
        tier = r.served_tier if r.ok else f"ERR:{(r.error or '')[:12]}"
        print(
            f"{text:<40} {r.prompt.expected_domain:<9} {tier:<9} "
            f"{(r.selected_model or '-'):<18} {(r.complexity or '-'):<12} "
            f"{r.latency_s:>6.2f} {r.cost:>10.6f}"
        )
    print(
        f"  -> ok={summary.ok_count}/{len(summary.results)} "
        f"avg_latency={summary.avg_latency:.2f}s "
        f"total_cost=${summary.total_cost:.6f} "
        f"cost/task=${summary.cost_per_task:.6f}"
    )


def routing_correct(results: list[CallResult]) -> tuple[int, int]:
    """(correct, total) — for ok calls, did the router's DECISION tier match the
    expected tier for the prompt's difficulty? Judged on the decision (not the
    served tier) so the classification is provable even without a frontier key."""
    correct = total = 0
    for r in results:
        if not r.ok:
            continue
        total += 1
        if r.decision_tier == expected_tier(r.prompt.expected_domain):
            correct += 1
    return correct, total


def all_local(results: list[CallResult]) -> bool:
    """True if every ok call stayed on the local tier (baseline expectation)."""
    return all(r.served_tier == "local" for r in results if r.ok)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="router_test A/B probe")
    ap.add_argument("--baseline-url", default="http://127.0.0.1:13399", help="proxy base URL with LEMON_ROUTER=off")
    ap.add_argument("--router-url", default="http://127.0.0.1:13398", help="proxy base URL with LEMON_ROUTER=on")
    ap.add_argument("--model", default=LOCAL_MODEL)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--mode", choices=["baseline", "router", "ab"], default="ab")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    summaries: list[Summary] = []
    if args.mode in ("baseline", "ab"):
        s = Summary("BASELINE (LEMON_ROUTER=off — all local)")
        for p in DEFAULT_PROMPTS:
            s.results.append(
                run_one(
                    p,
                    args.baseline_url,
                    router_on=False,
                    timeout=args.timeout,
                    max_tokens=args.max_tokens,
                    model=args.model,
                )
            )
        print_table(s)
        summaries.append(s)
    if args.mode in ("router", "ab"):
        s = Summary("ROUTER-ON (proxy consults the semantic router per prompt)")
        for p in DEFAULT_PROMPTS:
            s.results.append(
                run_one(
                    p,
                    args.router_url,
                    router_on=True,
                    timeout=args.timeout,
                    max_tokens=args.max_tokens,
                    model=args.model,
                )
            )
        print_table(s)
        summaries.append(s)
        correct, total = routing_correct(s.results)
        print(f"\nrouting correctness (router-on): {correct}/{total} prompts to expected tier")

    if len(summaries) == 2:
        base, routed = summaries[0], summaries[1]
        print("\n=== A/B DELTA ===")
        print(f"  baseline all-local  : {all_local(base.results)}")
        print(f"  baseline cost/task  : ${base.cost_per_task:.6f}")
        print(f"  router   cost/task  : ${routed.cost_per_task:.6f}")
        print(f"  baseline avg latency: {base.avg_latency:.2f}s")
        print(f"  router   avg latency: {routed.avg_latency:.2f}s")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(
                {
                    s.label: {
                        "ok": s.ok_count,
                        "total": len(s.results),
                        "avg_latency_s": s.avg_latency,
                        "total_cost_usd": s.total_cost,
                        "cost_per_task_usd": s.cost_per_task,
                        "results": [
                            {
                                "prompt": r.prompt.text,
                                "expected_domain": r.prompt.expected_domain,
                                "proxy_url": r.proxy_url,
                                "router_on": r.router_on,
                                "tier": r.served_tier,
                                "decision_tier": r.decision_tier,
                                "selected_model": r.selected_model,
                                "complexity": r.complexity,
                                "latency_s": r.latency_s,
                                "prompt_tokens": r.prompt_tokens,
                                "completion_tokens": r.completion_tokens,
                                "cost_usd": r.cost,
                                "status": r.status,
                                "ok": r.ok,
                                "error": r.error,
                            }
                            for r in s.results
                        ],
                    }
                    for s in summaries
                },
                f,
                indent=2,
            )
        print(f"\nwrote {args.json_out}")

    # Exit non-zero if any call failed, so the runner can gate on it.
    return 0 if all(r.ok for s in summaries for r in s.results) else 1


if __name__ == "__main__":
    sys.exit(main())
