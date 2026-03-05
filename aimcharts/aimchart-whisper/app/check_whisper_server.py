# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import base64
import uuid
from typing import Dict

import requests

_SAMPLE_AUDIO_URL = "https://paddlespeech.bj.bcebos.com/Parakeet/docs/demos/labixiaoxin.wav"
_DEFAULT_ENDPOINT = "http://localhost:7066/v1/asr"


def _fetch_audio_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.content


def _encode_audio(content: bytes) -> str:
    return base64.b64encode(content).decode("utf-8")


def prepare_test_payload() -> Dict[str, str]:
    """
    Retrieve a public audio sample and prepare JSON payload
    compatible with the ASR service.
    """
    request_id = uuid.uuid4().hex
    print(f"Preparing audio sample [{request_id}]")

    raw_audio = _fetch_audio_bytes(_SAMPLE_AUDIO_URL)
    encoded_audio = _encode_audio(raw_audio)

    return {"audio": encoded_audio}


def run_asr_check(endpoint: str = _DEFAULT_ENDPOINT) -> None:
    payload = prepare_test_payload()

    print(f"Sending request to {endpoint}")
    response = requests.post(
        endpoint,
        json=payload,
        timeout=30,
    )

    if response.ok:
        data = response.json()
        print("✅ Service responded successfully")
        print("📝 Transcription:", data.get("transcription", "<empty>"))
    else:
        print(f"❌ Request failed [{response.status_code}]")
        print(response.text)


if __name__ == "__main__":
    run_asr_check()
