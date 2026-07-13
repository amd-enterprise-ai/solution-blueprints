<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# RESULTS — client-side Lemonade (inference-plane) telemetry test

Status: ✅ **PASSED** on a Strix Halo deskside — 2026-07-01T08:40:29Z.

```
host=<halo-host>  node=v24.18.0
inference: proxy -> Lemonade Qwen3-8B-GGUF on CPU (:13305)
audit: real Splunk index=axis sourcetype=axis:llm
splunk_up=1  defenseclaw_up=1  lemonade_up=1
pass=12  fail=0
cc=ok
```

Both the deterministic curl probe (session `lemon-probe`) and Claude Code routed
through the proxy (session `cc-lemon`) landed `llm.request(decision=allow)` events
in the real Splunk `index=axis`, each carrying a DefenseClaw prompt verdict
(`action=allow`). The proxy forwarded `/v1/messages` byte-for-byte — the client
saw an unmodified Lemonade completion.

## Checks

| Stage | Check | Result |
|-------|-------|--------|
| 0 | proxy unit tests (22) green | ✅ |
| 1 | real Splunk reused; HEC + mgmt/search healthy | ✅ |
| 2 | DefenseClaw gateway healthy on :18970 | ✅ |
| 3 | Lemonade healthy on :13305 (Qwen3-8B, CPU) | ✅ |
| 4 | telemetry proxy healthy (transparent passthrough) | ✅ |
| 5 | proxy returned a real Lemonade completion | ✅ |
| 5 | `llm.session_start` CONFIRMED in `index=axis` | ✅ |
| 5 | `llm.request(decision=allow)` (session `lemon-probe`) CONFIRMED in `index=axis` | ✅ |
| 5 | `llm.request` carries a DefenseClaw prompt verdict | ✅ |
| 6 | [cc] Claude Code inference through the proxy → `llm.request` (session `cc-lemon`) in Splunk | ✅ (`cc=ok`) |

## Splunk read-back (search API)

```
2026-07-01 08:39:42.680 UTC  llm.session_start    (session lemon-probe)
2026-07-01 08:39:43.652 UTC  llm.request  decision=allow  (session lemon-probe)
2026-07-01 08:39:45.938 UTC  llm.session_end      (session lemon-probe)
2026-07-01 08:39:47.618 UTC  llm.session_start    (session cc-lemon)
2026-07-01 08:40:25.778 UTC  llm.request  decision=allow  (session cc-lemon)
2026-07-01 08:40:27.956 UTC  llm.session_end      (session cc-lemon)

6 events returned from Splunk index
```

Sample `llm.request` (metadata only — no prompt/completion text):

```json
{"event":"llm.request","identity":{"session":"lemon-probe","user":"amd","tenant":"client-deskside","device_id":"<halo-host>"},
 "policy":{"id":"inference-proxy","source":"local-control"},
 "request":{"seq":0,"model":"Qwen3-8B-GGUF","endpoint":"/v1/messages","stream":false,"messages":1,"prompt_chars":34},
 "decision":"allow",
 "result":{"status":200,"duration_ms":965,"prompt_tokens":16,"completion_tokens":32,"stop_reason":"max_tokens"},
 "defenseclaw_request":{"action":"allow","severity":"NONE","findings":[],"would_block":false,"reachable":true},
 "defenseclaw_response":null}
```

## Artifacts

Saved under `artifacts/node_run/`: `SUMMARY.txt`, `events.jsonl`,
`splunk_query.txt`, `proxy_probe.json`, `proxy_probe.log`, `proxy_cc.log`,
`claude_cc.out`, `claude_cc.err`, `gateway_boot.txt`, `proxy_unit_tests.log`.

---

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
