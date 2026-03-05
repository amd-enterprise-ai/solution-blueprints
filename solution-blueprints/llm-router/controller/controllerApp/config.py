# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os

import yaml


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        content = f.read()
    for k, v in os.environ.items():
        content = content.replace("${" + k + "}", v)
    return yaml.safe_load(content)


def mask_config(config: dict) -> dict:
    config_out = dict(config)
    for policy in config_out.get("routing_rules", []):
        for llm in policy.get("models", []):
            if "access_key" in llm:
                llm["access_key"] = "[REDACTED]"
    return config_out
