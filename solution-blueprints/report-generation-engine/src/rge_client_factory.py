# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Client factory module.

Initializes LLM and Tavily clients with proper configuration.
"""

import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from rge_config import Config
from tavily import AsyncTavilyClient

logger = logging.getLogger(__name__)


def create_llm_client(config: Config) -> Any:
    """
    Create and configure LLM client.
    Args:
        config: Configuration instance with credentials and settings

    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        model=config.llm_model,
        base_url=config.llm_base_url,
        api_key="dummy",  # For local AMD AIM deployments
        temperature=config.llm_temperature,
    )


def create_tavily_client(config: Config) -> Optional[AsyncTavilyClient]:
    """
    Create and configure Tavily client.
    Args:
        config: Configuration instance with API key

    Returns:
        Configured AsyncTavilyClient instance, or None if no API key configured
    """
    if not config.tavily_api_key:
        logger.warning("Tavily client not created - no API key configured")
        return None
    return AsyncTavilyClient(api_key=config.tavily_api_key)


if __name__ == "__main__":
    """Test client initialization."""
    from rge_config import get_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    try:
        logger.info("Loading configuration...")
        config = get_config()

        logger.info("Initializing clients...")
        llm = create_llm_client(config)
        tavily = create_tavily_client(config)

        logger.info("LLM client initialized successfully")
        logger.info(f"  Model: {config.llm_model}")
        logger.info(f"  Temperature: {config.llm_temperature}")
        logger.info(f"  Client type: {type(llm).__name__}")

        logger.info("Tavily client initialized successfully")
        logger.info(f"  Client type: {type(tavily).__name__}")

    except Exception as e:
        logger.error(f"Error: {e}")
