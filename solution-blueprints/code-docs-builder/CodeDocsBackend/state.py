# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import aimclient
import pipelines
from crewai import Crew


class CrewsConfiguration:
    roadmap_crew: Crew
    documentation_crew: Crew

    def __init__(self, roadmap_crew: Crew, documentation_crew: Crew):
        self.roadmap_crew = roadmap_crew
        self.documentation_crew = documentation_crew


# Store documentation status by repository ID
documentation_status: dict[str, str] = {}
# Store configured crews for documentation generation process
_crews_configuration: CrewsConfiguration | None = None


def get_crews_configuration() -> CrewsConfiguration:
    """
    Get configured crews for repository generation process.
    1. Fetch available model from AIM.
    2. Initialize LLM.
    3. Initialize roadmap crew.
    4. Initialize documentation crew.
    5. Create and return crews configuration.

    Returns:
        CrewsConfiguration: Configured crews
    """
    global _crews_configuration

    if _crews_configuration is None:
        model = aimclient.fetch_available_model()
        llm = pipelines.create_llm(model)
        roadmap_crew = pipelines.create_roadmap_crew(llm=llm)
        documentation_crew = pipelines.create_documentation_crew(llm=llm)

        _crews_configuration = CrewsConfiguration(roadmap_crew=roadmap_crew, documentation_crew=documentation_crew)

    return _crews_configuration
