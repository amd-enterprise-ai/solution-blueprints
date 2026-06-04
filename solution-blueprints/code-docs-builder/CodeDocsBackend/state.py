# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import aimclient
import pipelines
from crewai import LLM


class LLMConfiguration:
    model: str
    llm: LLM

    def __init__(self, model: str, llm: LLM):
        self.model = model
        self.llm = llm


# Store documentation status by repository ID
documentation_status: dict[str, str] = {}
# Store configured LLM for documentation analysis, generation and audit purpose
_llm_configuration: LLMConfiguration | None = None


def get_llm_configuration() -> LLMConfiguration:
    """
    Get configured LLM. Initializes only once. Then returns previously created instance.
    1. Fetch available model from AIM.
    2. Initialize LLM.
    3. Create and return LLM configuration.

    Returns:
        LLMConfiguration: Configured LLM
    """
    global _llm_configuration
    if _llm_configuration is None:
        model = aimclient.fetch_available_model()
        llm = pipelines.create_llm(model)

        _llm_configuration = LLMConfiguration(model=model, llm=llm)

    return _llm_configuration
