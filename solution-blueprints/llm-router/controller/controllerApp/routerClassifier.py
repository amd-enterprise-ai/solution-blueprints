# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json

import httpx


async def classify(messages: list, classes: list, url: str) -> str:
    payload = {
        "messages": messages,
        "classes": classes,
    }

    print(f"[router_classifier] POST {url} with payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json=payload)
        except Exception as e:
            print(f"[router_classifier] Exception while requesting classifier: {e}")
            raise Exception(f"Classifier HTTP error: {e}")

    print(f"[router_classifier] Classifier status={response.status_code}")
    print("[router_classifier] Classifier raw response:", response.text)

    try:
        data = response.json()
    except Exception as e:
        print(f"[router_classifier] Exception during .json(): {e}")
        raise Exception(f"Classifier invalid json: {e}, body={response.text}")

    print("[router_classifier] Classifier decoded response:", data)

    if response.status_code != 200:
        raise Exception(f"Classifier service error, status={response.status_code}, body={data}")

    chosen_class = data.get("chosen_class")
    if not chosen_class:
        raise Exception(f"Classifier returned empty selection, body={data}")

    return chosen_class
