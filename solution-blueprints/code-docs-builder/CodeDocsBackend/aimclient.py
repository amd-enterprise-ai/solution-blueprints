# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os
import time

import requests

logger = logging.getLogger("backend")


def fetch_available_model(poll_interval: int = 30) -> str:
    """
    Fetch available LLM names from AIM service. Returns first from list.

    Args:
        poll_interval: Polling interval in seconds.

    Returns:
        str: First available LLM name from AIM service
    """

    base_url = os.environ.get("AMD_AIM_BASE_URL")
    url = f"{base_url}/models"

    while True:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    logging.info("Available model is '%s'", data[0]["id"])
                    return data[0]["id"]
        except requests.RequestException:
            logger.info("LLM is not yet initialized. Waiting for retry in %s seconds", poll_interval)

        time.sleep(poll_interval)
