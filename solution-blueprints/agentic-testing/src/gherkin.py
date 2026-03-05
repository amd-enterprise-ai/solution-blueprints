# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Gherkin feature file parsing."""

import re
from dataclasses import dataclass


@dataclass
class Scenario:
    """A single test scenario parsed from Gherkin."""

    name: str
    tags: list[str]
    steps: str  # The full Given/When/Then text


@dataclass
class Feature:
    """A Gherkin feature with background and scenarios."""

    name: str
    description: str
    background: str
    scenarios: list[Scenario]


def parse_gherkin(text: str) -> Feature:
    """Parse Gherkin-style feature file into structured data."""
    lines = text.strip().split("\n")

    feature_name = ""
    feature_desc_lines = []
    background_lines: list[str] = []
    scenarios: list[Scenario] = []

    current_section: str | None = None
    current_scenario_name = ""
    current_scenario_tags: list[str] = []
    current_scenario_lines: list[str] = []
    pending_tags: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Tags (e.g., @search, @navigation)
        if stripped.startswith("@"):
            pending_tags.extend(re.findall(r"@(\w+)", stripped))
            continue

        # Feature declaration
        if stripped.startswith("Feature:"):
            feature_name = stripped[8:].strip()
            current_section = "feature"
            continue

        # Background section
        if stripped.startswith("Background:"):
            # Save any pending scenario
            if current_scenario_name and current_scenario_lines:
                scenarios.append(
                    Scenario(
                        name=current_scenario_name, tags=current_scenario_tags, steps="\n".join(current_scenario_lines)
                    )
                )
                current_scenario_name = ""
                current_scenario_tags = []
                current_scenario_lines = []
            current_section = "background"
            continue

        # Scenario declaration
        if stripped.startswith("Scenario:"):
            # Save previous scenario if exists
            if current_scenario_name and current_scenario_lines:
                scenarios.append(
                    Scenario(
                        name=current_scenario_name, tags=current_scenario_tags, steps="\n".join(current_scenario_lines)
                    )
                )
            current_scenario_name = stripped[9:].strip()
            current_scenario_tags = pending_tags
            current_scenario_lines = []
            pending_tags = []
            current_section = "scenario"
            continue

        # Content lines (Given/When/Then/And or description)
        if current_section == "feature":
            feature_desc_lines.append(stripped)
        elif current_section == "background":
            background_lines.append(stripped)
        elif current_section == "scenario":
            current_scenario_lines.append(stripped)

    # Save last scenario
    if current_scenario_name and current_scenario_lines:
        scenarios.append(
            Scenario(name=current_scenario_name, tags=current_scenario_tags, steps="\n".join(current_scenario_lines))
        )

    return Feature(
        name=feature_name,
        description="\n".join(feature_desc_lines),
        background="\n".join(background_lines),
        scenarios=scenarios,
    )
