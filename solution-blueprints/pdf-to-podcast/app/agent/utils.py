# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Utilities for LLM model configuration."""

import asyncio
import logging
import urllib.parse

import httpx
from agent.chat_llm import ChatLLM

logger = logging.getLogger(__name__)
_llm_cache: ChatLLM | None = None

INIT_RETRIES = 30


async def init_llm(base_url: str, api_key: str) -> ChatLLM:
    """Initialize the LLM.

    Fetches the model information from the model listing endpoint with retry logic.

    Args:
        base_url (str): Base URL of the LLM service
        api_key (str): API key for authentication

    Returns:
        ChatLLM: Initialized ChatLLM instance

    Raises:
        RuntimeError: If model name cannot be retrieved after all retries

    """
    global _llm_cache

    # Return cached instance if available
    if _llm_cache is not None:
        return _llm_cache

    models_url = urllib.parse.urljoin(base_url, "v1/models")
    headers = {}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for retry in range(INIT_RETRIES):
        if retry != 0:
            logger.warning("Couldn't retrieve model name - LLM probably not up yet. Waiting 2 seconds...")
            await asyncio.sleep(2)

        logger.info("Trying to retrieve model name (attempt %d)", retry + 1)

        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                response = await client.get(models_url, headers=headers)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        model_name = data["data"][0]["id"]

                        llm = ChatLLM(
                            model=model_name,
                            base_url=base_url,
                            api_key=api_key,
                            max_tokens=None,
                        )

                        # Cache the initialized LLM
                        _llm_cache = llm
                        logger.info("Successfully initialized LLM with model: %s", model_name)
                        return llm

                    except (KeyError, IndexError, TypeError) as exc:
                        logger.error("Invalid response format: %s", response.content)
                        raise RuntimeError(
                            f"Failed to retrieve model name, Invalid response format: {response.content}"
                        ) from exc

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as exc:
            logger.debug("Connection error (attempt %d): %s", retry + 1, exc)

        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP error (attempt %d): %s", retry + 1, exc)

        except Exception as exc:
            logger.warning("Unexpected error (attempt %d): %s", retry + 1, exc)

    raise RuntimeError("Failed to retrieve model name after all retry attempts")
