# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Configuration loader using environment variables.
Loads prompts from prompts.yaml, all other config from env vars.
"""

import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

import requests
import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    """Simple config container with all settings as attributes."""

    # API Keys
    tavily_api_key: str
    langchain_api_key: Optional[str]

    # LLM Configuration
    llm_base_url: str
    llm_model: str
    llm_temperature: float
    llm_max_retries: int

    # LangSmith Configuration
    langchain_tracing_v2: bool
    langchain_project: str

    # Search Configuration
    number_of_queries: int
    tavily_topic: str
    tavily_days: Optional[int]
    tavily_max_results: int

    # Generation Configuration
    max_section_length: int
    final_section_length: int
    planning_context_chars: int
    section_context_chars: int

    # API/UI Configuration
    api_port: int
    ui_port: int
    api_host: str
    api_base_url: str

    # Prompts
    prompts: Dict[str, str]
    default_topic: str
    default_report_structure: str


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes")


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer for {key}: {value}, using default: {default}")
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid float for {key}: {value}, using default: {default}")
        return default


def _get_env_optional_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Get optional integer from environment variable."""
    value = os.getenv(key)
    if value is None or value == "" or value.lower() == "null":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer for {key}: {value}, using default: {default}")
        return default


INIT_RETRIES = 180  # 180 retries × 10 seconds = 30 minutes
INIT_RETRY_INTERVAL = 10  # seconds between retries


def _init_model(base_url: str) -> str:
    """Auto-detect model from vLLM /v1/models endpoint."""
    start_time = time.time()
    model_id: str = ""

    for retry in range(INIT_RETRIES):
        elapsed = int(time.time() - start_time)

        # Log every attempt (including first)
        logger.info(
            "Connecting to LLM service at %s (attempt %d/%d, elapsed %ds)",
            base_url,
            retry + 1,
            INIT_RETRIES,
            elapsed,
        )

        try:
            # Ensure base_url ends with / for proper path joining
            base = base_url if base_url.endswith("/") else base_url + "/"
            url = urllib.parse.urljoin(base, "models")
            r = requests.get(url, timeout=5.0)
            if r.status_code == 200:
                model_id = r.json()["data"][0]["id"]
                logger.info("Auto-detected model: %s", model_id)
                break
        except requests.exceptions.ConnectionError as e:
            logger.debug("LLM service not available yet: %s", e)
        except (KeyError, IndexError) as e:
            logger.warning("Invalid response from /v1/models: %s", e)

        # Sleep before next retry (except on last attempt)
        if retry < INIT_RETRIES - 1:
            time.sleep(INIT_RETRY_INTERVAL)
    else:
        # Loop exhausted without break — LLM never became available
        logger.error(
            "LLM service not available at %s after %d attempts (%d minutes). Exiting.",
            base_url,
            INIT_RETRIES,
            INIT_RETRIES * INIT_RETRY_INTERVAL // 60,
        )
        sys.exit(1)

    return model_id


def load_config(prompts_file: Path = None, env_file: Path = None) -> Config:
    """
    Load configuration from environment variables and prompts.yaml.

    Args:
        prompts_file: Path to prompts.yaml (default: src/prompts.yaml)
        env_file: Path to .env file (default: src/.env)

    Returns:
        Config object with all settings as attributes

    Exits with error if required fields are missing.
    """
    # Default paths
    if prompts_file is None:
        prompts_file = Path(__file__).parent / "prompts.yaml"
    if env_file is None:
        env_file = Path(__file__).parent / ".env"

    # Load .env first (for local development)
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("Loaded .env from: %s", env_file)

    # Create config object
    config = Config()

    # ==========================================
    # Load from environment variables
    # ==========================================

    # API Keys
    config.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    config.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")

    # LLM Configuration
    config.llm_base_url = os.getenv("OPENAI_API_BASE_URL", "")
    if not config.llm_base_url:
        logger.error("OPENAI_API_BASE_URL is required but not set")
        sys.exit(1)
    config.llm_model = _init_model(config.llm_base_url)
    config.llm_temperature = _get_env_float("LLM_TEMPERATURE", 0.6)
    config.llm_max_retries = _get_env_int("LLM_MAX_RETRIES", 3)

    # LangSmith Configuration
    config.langchain_tracing_v2 = _get_env_bool("LANGSMITH_TRACING_ENABLED", False)
    config.langchain_project = os.getenv("LANGSMITH_PROJECT", "report-generation-engine")

    # Search Configuration
    config.number_of_queries = _get_env_int("SEARCH_NUMBER_OF_QUERIES", 2)
    config.tavily_topic = os.getenv("SEARCH_TAVILY_TOPIC", "general")
    config.tavily_days = _get_env_optional_int("SEARCH_TAVILY_DAYS", None)
    config.tavily_max_results = _get_env_int("SEARCH_TAVILY_MAX_RESULTS", 5)

    # Generation Configuration
    config.max_section_length = _get_env_int("GENERATION_MAX_SECTION_LENGTH", 1000)
    config.final_section_length = _get_env_int("GENERATION_FINAL_SECTION_LENGTH", 300)
    config.planning_context_chars = _get_env_int("GENERATION_PLANNING_CONTEXT_CHARS", 5000)
    config.section_context_chars = _get_env_int("GENERATION_SECTION_CONTEXT_CHARS", 8000)

    # API/UI Configuration
    config.api_port = _get_env_int("API_PORT", 8000)
    config.ui_port = _get_env_int("UI_PORT", 8501)
    config.api_host = "0.0.0.0"
    config.api_base_url = f"http://localhost:{config.api_port}"

    # ==========================================
    # Load prompts from prompts.yaml
    # ==========================================
    if prompts_file.exists():
        with open(prompts_file, "r") as f:
            yaml_data = yaml.safe_load(f)
        logger.info(f"Loaded prompts from: {prompts_file}")

        prompts = yaml_data.get("prompts", {})
        config.prompts = prompts.get("templates", {})
        defaults = prompts.get("defaults", {})
        config.default_topic = defaults.get("topic", "")
        config.default_report_structure = defaults.get("report_structure", "")
    else:
        logger.warning(f"No prompts file found at: {prompts_file}, using empty prompts")
        config.prompts = {}
        config.default_topic = os.getenv("DEFAULT_TOPIC", "")
        config.default_report_structure = os.getenv("DEFAULT_REPORT_STRUCTURE", "")

    # Log loaded config
    logger.info("Configuration loaded successfully")
    logger.info("LLM: %s @ %s", config.llm_model, config.llm_base_url)
    logger.info("Temperature: %s", config.llm_temperature)
    if config.tavily_api_key:
        logger.info("Tavily API: Configured")
    else:
        logger.warning("Tavily API: NOT CONFIGURED - report generation will fail")
    logger.info("Queries per section: %s", config.number_of_queries)
    logger.info("Max section length: %s words", config.max_section_length)
    logger.info("API port: %s, UI port: %s", config.api_port, config.ui_port)

    if config.langchain_api_key:
        logger.info("LangSmith: Enabled (project: %s)", config.langchain_project)
    else:
        logger.info("LangSmith: Disabled")

    return config


# Singleton instance
_config = None


def get_config(prompts_file: Path = None, env_file: Path = None) -> Config:
    """
    Get config singleton. Loads on first call, returns cached instance after.
    """
    global _config
    if _config is None:
        _config = load_config(prompts_file, env_file)
    return _config


if __name__ == "__main__":
    """Test configuration loading."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    config = load_config()
    logger.info(f"Configuration test passed! Using model: {config.llm_model}")
