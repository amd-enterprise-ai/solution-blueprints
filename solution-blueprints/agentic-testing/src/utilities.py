# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Utility functions for the agentic testing agent."""

import re
import time
import urllib.parse

import requests


def check_service_ready(url: str, timeout: int = 5) -> bool:
    """Check if a service is ready by making a GET request."""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def fetch_model_name(base_url: str, max_retries: int = 60, retry_delay: int = 5) -> str | None:
    """Fetch model name from AIM service /v1/models endpoint."""
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    models_url = urllib.parse.urljoin(base_url, "models")

    for retry in range(max_retries):
        try:
            r = requests.get(models_url, timeout=5)
            if r.status_code == 200:
                try:
                    return r.json()["data"][0]["id"]
                except (KeyError, IndexError):
                    # Malformed or unexpected response; treat as "no model yet" and retry.
                    continue
        except requests.exceptions.RequestException:
            # Connectivity issue, continue retrying until max_retries is reached.
            pass
        if retry < max_retries - 1:
            time.sleep(retry_delay)
    return None


def strip_copyright_header(text: str) -> str:
    """Remove copyright header lines from text."""
    lines = text.split("\n")
    # Skip lines that are part of the copyright header
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and any(
            keyword in stripped.lower() for keyword in ["copyright", "spdx", "license", "spdx-license"]
        ):
            start_idx = i + 1
        elif stripped == "#":
            # Empty comment line, might be part of header
            start_idx = i + 1
        elif stripped == "":
            # Empty line after header
            if start_idx > 0:
                start_idx = i + 1
                break
        else:
            # Non-header content found
            break
    return "\n".join(lines[start_idx:]).strip()


def clean_tool_name(name: str) -> str:
    """Remove any garbage tokens from tool names."""
    return re.split(r"<\|", name)[0].strip()


def extract_playwright_code(tool_result: str) -> str | None:
    """Extract Playwright code from MCP tool result."""
    # Look for "### Ran Playwright code" section
    match = re.search(r"### Ran Playwright code\n(.+?)(?:\n###|\n\n|$)", tool_result, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
