# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os
import time

import requests

logger = logging.getLogger("backend")


def _normalize_base_url(raw_base_url: str | None) -> str:
    if not raw_base_url:
        raise RuntimeError("AMD_AIM_BASE_URL is not set")

    base_url = raw_base_url.strip().rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def fetch_available_model(poll_interval: int = 30) -> str:
    """
    Fetch available LLM names from AIM service. Returns first from list.

    Args:
        poll_interval: Polling interval in seconds.

    Returns:
        str: First available LLM name from AIM service
    """

    override_model = os.environ.get("AMD_AIM_MODEL")
    if override_model:
        logging.info("Using configured model '%s'", override_model)
        return override_model

    base_url = _normalize_base_url(os.environ.get("AMD_AIM_BASE_URL"))
    url = f"{base_url}/models"
    api_key = os.environ.get("AMD_AIM_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    max_wait_seconds = int(os.environ.get("AMD_AIM_MODEL_INIT_TIMEOUT", "1800"))
    deadline = time.time() + max_wait_seconds

    while True:
        if time.time() >= deadline:
            raise TimeoutError(
                "Timed out waiting for model initialization at "
                f"{url}. Verify AMD_AIM_BASE_URL/API key or set AMD_AIM_MODEL to bypass discovery."
            )

        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    logging.info("Available model is '%s'", data[0]["id"])
                    return data[0]["id"]
                logger.info("Models endpoint returned 200 but no models yet. Waiting %s seconds", poll_interval)
            else:
                body = response.text[:300].replace("\n", " ")
                logger.warning(
                    "Models endpoint not ready (%s). Waiting %s seconds. URL=%s Response=%s",
                    response.status_code,
                    poll_interval,
                    url,
                    body,
                )
        except requests.RequestException as exc:
            logger.warning(
                "Failed to query models endpoint. Waiting %s seconds. URL=%s Error=%s",
                poll_interval,
                url,
                exc,
            )

        time.sleep(poll_interval)
