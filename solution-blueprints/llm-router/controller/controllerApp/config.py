# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import copy
import logging
import os

import yaml

logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    logger.info("=== START load_config() ===")
    logger.info("CONFIG_PATH: %s", path)

    with open(path, "r") as f:
        content = f.read()
    logger.debug("Read %d bytes from config file", len(content))

    # Check for LLM_API_KEY env vars
    llm_keys = {k: v for k, v in os.environ.items() if "LLM_API_KEY" in k}
    logger.info("Found %d LLM_API_KEY_* env vars: %s", len(llm_keys), list(llm_keys.keys()))

    # Perform substitution
    original_content = content
    for k, v in os.environ.items():
        old_placeholder = "${" + k + "}"
        if old_placeholder in content:
            logger.info("Replacing placeholder: %s", old_placeholder)
            content = content.replace(old_placeholder, v)

    # Check if any placeholders remain
    remaining_placeholders = [s for s in content.split("${") if "}" in s]
    if remaining_placeholders:
        logger.warning(
            "Found %d remaining ${...} placeholders after substitution: %s",
            len(remaining_placeholders),
            remaining_placeholders[:5],
        )
    else:
        logger.info("No remaining ${...} placeholders after substitution")

    logger.info("Content modified: %s", original_content != content)
    logger.info("=== END load_config() ===")

    return yaml.safe_load(content)


def mask_config(config: dict) -> dict:
    # Use deep copy to avoid mutating the cached runtime config when redacting.
    config_out = copy.deepcopy(config)
    for policy in config_out.get("routing_rules", []):
        for llm in policy.get("models", []):
            if "api_key" in llm:
                llm["api_key"] = "[REDACTED]"
    return config_out
