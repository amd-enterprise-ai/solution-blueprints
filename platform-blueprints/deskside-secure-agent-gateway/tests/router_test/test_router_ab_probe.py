# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the router_test A/B probe.

No network: urllib.request.urlopen is monkeypatched to a fake proxy that sets the
x-lemon-* routing headers per prompt difficulty, so these run anywhere without the
proxy, Lemonade, or the semantic router.
"""
from __future__ import annotations

import json

import router_ab_probe as rp

# --- pure helpers -----------------------------------------------------------


def test_cost_local_is_free():
    assert rp.cost_usd("local", 1000, 1000) == 0.0


def test_cost_frontier_matches_pricing():
    # 1M prompt tok @ $15 + 1M completion tok @ $75 = $90.
    assert rp.cost_usd("frontier", 1_000_000, 1_000_000) == 90.0


def test_cost_unknown_tier_is_free():
    assert rp.cost_usd("mystery", 5000, 5000) == 0.0


def test_model_tier_mapping():
    assert rp.model_tier("claude-opus-4.8") == "frontier"
    assert rp.model_tier("lemonade-local") == "local"
    assert rp.model_tier("") == "local"


def test_expected_tier_mapping():
    assert rp.expected_tier("simple") == "local"
    assert rp.expected_tier("reasoning") == "frontier"
    assert rp.expected_tier("anything-else") == "local"


def test_routing_from_headers_case_insensitive():
    r = rp.routing_from_headers(
        {
            "X-Lemon-Router": "on",
            "x-lemon-tier": "frontier",
            "X-Lemon-Selected-Model": "claude-opus-4.8",
            "x-lemon-complexity": "needs_reasoning:hard",
        }
    )
    assert r["router"] == "on"
    assert r["tier"] == "frontier"
    assert r["selected_model"] == "claude-opus-4.8"
    assert r["complexity"] == "needs_reasoning:hard"


def test_routing_from_headers_missing():
    r = rp.routing_from_headers({})
    assert r == {"router": None, "tier": None, "selected_model": None, "complexity": None}


# --- mocked end-to-end (no network) -----------------------------------------


class _FakeResp:
    def __init__(self, status, body, headers):
        self.status = status
        self._body = json.dumps(body).encode()
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake(monkeypatch, router_on):
    """Patch urlopen to emulate the proxy: baseline (router off) always returns
    tier=local; router-on returns tier=frontier for hard prompts, local else."""

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode())
        text = payload["messages"][0]["content"].lower()
        hard = any(k in text for k in ("prove", "algorithm", "plan the"))
        if router_on and hard:
            headers = {
                "x-lemon-router": "on",
                "x-lemon-tier": "frontier",
                "x-lemon-selected-model": "claude-opus-4.8",
                "x-lemon-complexity": "needs_reasoning:hard",
            }
            usage = {"input_tokens": 50, "output_tokens": 200}
        elif router_on:
            headers = {
                "x-lemon-router": "on",
                "x-lemon-tier": "local",
                "x-lemon-selected-model": "lemonade-local",
                "x-lemon-complexity": "needs_reasoning:easy",
            }
            usage = {"input_tokens": 50, "output_tokens": 20}
        else:
            headers = {"x-lemon-router": "off", "x-lemon-tier": "local"}
            usage = {"input_tokens": 50, "output_tokens": 20}
        return _FakeResp(
            200,
            {"type": "message", "content": [{"type": "text", "text": "ok"}], "usage": usage},
            headers,
        )

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)


def test_baseline_keeps_everything_local(monkeypatch):
    _install_fake(monkeypatch, router_on=False)
    results = [rp.run_one(p, "http://proxy", router_on=False, timeout=5, max_tokens=16) for p in rp.DEFAULT_PROMPTS]
    assert all(r.ok for r in results)
    assert rp.all_local(results)
    assert sum(r.cost for r in results) == 0.0


def test_router_on_sends_hard_prompts_to_frontier(monkeypatch):
    _install_fake(monkeypatch, router_on=True)
    results = [rp.run_one(p, "http://proxy", router_on=True, timeout=5, max_tokens=16) for p in rp.DEFAULT_PROMPTS]
    assert all(r.ok for r in results)
    correct, total = rp.routing_correct(results)
    assert total == len(rp.DEFAULT_PROMPTS)
    assert correct == total  # the fake proxy routes exactly per expected_domain
    # At least one frontier call -> non-zero total cost.
    assert sum(r.cost for r in results) > 0.0
    # The three reasoning prompts escalate.
    frontier = [r for r in results if r.served_tier == "frontier"]
    assert len(frontier) == 3


def test_router_on_reads_headers(monkeypatch):
    _install_fake(monkeypatch, router_on=True)
    hard = rp.run_one(rp.DEFAULT_PROMPTS[4], "http://proxy", router_on=True, timeout=5, max_tokens=16)
    assert hard.served_tier == "frontier"
    assert hard.selected_model == "claude-opus-4.8"
    assert hard.complexity == "needs_reasoning:hard"


def test_decision_tier_provable_without_frontier_key(monkeypatch):
    """Router picks frontier (selected_model=claude-*) but the proxy has no key,
    so it serves local. decision_tier must still read 'frontier' and routing be
    judged correct."""

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode())
        text = payload["messages"][0]["content"].lower()
        hard = any(k in text for k in ("prove", "algorithm", "plan the"))
        if hard:
            # Router decided frontier, but proxy fell back to local (no key).
            headers = {
                "x-lemon-router": "on",
                "x-lemon-tier": "local",
                "x-lemon-selected-model": "claude-opus-4.8",
                "x-lemon-complexity": "needs_reasoning:hard",
            }
        else:
            headers = {"x-lemon-router": "on", "x-lemon-tier": "local", "x-lemon-selected-model": "lemonade-local"}
        return _FakeResp(
            200, {"type": "message", "content": [], "usage": {"input_tokens": 10, "output_tokens": 10}}, headers
        )

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)
    results = [rp.run_one(p, "http://proxy", router_on=True, timeout=5, max_tokens=16) for p in rp.DEFAULT_PROMPTS]
    # Everything served local (no key), but the DECISION correctly split 4/3.
    assert rp.all_local(results)
    correct, total = rp.routing_correct(results)
    assert correct == total == len(rp.DEFAULT_PROMPTS)
    assert sum(1 for r in results if r.decision_tier == "frontier") == 3


def test_main_ab_mocked_runs_clean(monkeypatch, tmp_path):
    # In ab mode both passes hit the same fake; router-on behavior is keyed on the
    # request, so patch with router_on=True (baseline pass still reports local via
    # the header the fake sets for non-hard... use a difficulty-only fake).
    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode())
        text = payload["messages"][0]["content"].lower()
        hard = any(k in text for k in ("prove", "algorithm", "plan the"))
        # Emulate: this fake proxy has the router ON, so it escalates hard prompts.
        if hard:
            headers = {"x-lemon-router": "on", "x-lemon-tier": "frontier", "x-lemon-selected-model": "claude-opus-4.8"}
            usage = {"input_tokens": 50, "output_tokens": 200}
        else:
            headers = {"x-lemon-router": "on", "x-lemon-tier": "local"}
            usage = {"input_tokens": 50, "output_tokens": 20}
        return _FakeResp(200, {"type": "message", "content": [], "usage": usage}, headers)

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)
    out = tmp_path / "ab.json"
    rc = rp.main(
        [
            "--baseline-url",
            "http://proxy",
            "--router-url",
            "http://proxy",
            "--mode",
            "ab",
            "--timeout",
            "5",
            "--max-tokens",
            "16",
            "--json-out",
            str(out),
        ]
    )
    assert rc == 0
    data = json.loads(out.read_text())
    assert len(data) == 2  # baseline + router summaries
