# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Any, Optional, Type

import yaml
from crewai import LLM, Agent, Crew, Task
from crewai_tools import DirectoryReadTool, FileReadTool
from pydantic import BaseModel

documentation_agents_config_path = os.getenv(
    key="DOCUMENTATION_AGENTS_CONFIG", default="./config/documentation/agents.yaml"
)
documentation_tasks_config_path = os.getenv(
    key="DOCUMENTATION_TASKS_CONFIG", default="./config/documentation/tasks.yaml"
)
roadmap_agents_config_path = os.getenv(key="PLANNER_AGENTS_CONFIG", default="./config/roadmap/agents.yaml")
roadmap_tasks_config_path = os.getenv(key="PLANNER_TASKS_CONFIG", default="./config/roadmap/tasks.yaml")


class DocumentationSection(BaseModel):
    """
    Single documentation section describing one specific topic or feature.

    Attributes:
        title: Short name of the section.
        description: Detailed explanation of what this section covers.
        prerequisites: Requirements or assumptions needed to understand or use this part.
        examples: List of usage examples, code snippets, or scenarios.
        goal: Main outcome or learning objective for this section.
    """

    title: str
    description: str
    prerequisites: str
    examples: list[str]
    goal: str


class DocumentationPlan(BaseModel):
    """
    High-level documentation plan generated from the codebase analysis.

    Attributes:
        overview: General overview of the project or documentation scope.
        sections: List of structured documentation sections to be written.
    """

    overview: str
    sections: list[DocumentationSection]


def create_llm(model: str) -> LLM:
    """
    Create an LLM client configured to route requests to the AMD AIM service.

    The configuration is pulled from environment variables:
    - AMD_AIM_BASE_URL
    - AMD_AIM_API_KEY

    Args:
        model: LLM model name (fetched from AIM service).

    Returns:
        LLM: Configured LLM client instance.
    """

    return LLM(
        model=f"openai/{model}",
        base_url=os.getenv("AMD_AIM_BASE_URL"),
        api_key=os.getenv("AMD_AIM_API_KEY"),
        temperature=0.2,
        timeout=300,
    )


def _create_agent(config: dict[str, Any], llm: LLM) -> Agent:
    """
    Create a CrewAI Agent with shared defaults.

    Args:
        config: Agent configuration loaded from YAML.
        llm: Preconfigured LLM instance used by the agent.

    Returns:
        Agent: Initialized Agent instance ready to be used in a crew.
    """

    return Agent(
        config=config,
        system_template="""<|begin_of_text|><|start_header_id|>system<|end_header_id|>{{ .System }}<|eot_id|>""",
        prompt_template="""<|start_header_id|>user<|end_header_id|>{{ .Prompt }}<|eot_id|>""",
        response_template="""<|start_header_id|>assistant<|end_header_id|>{{ .Response }}<|eot_id|>""",
        tools=[DirectoryReadTool(), FileReadTool()],
        llm=llm,
    )


def _create_task(
    config: dict[str, Any],
    agent: Agent,
    output_pydantic: Optional[Type[BaseModel]] = None,
    max_retries: Optional[int] = None,
) -> Task:
    """
    Create a CrewAI Task with optional output model and retry policy.

    Args:
        config: Task configuration loaded from YAML.
        agent: Agent responsible for executing this task.
        output_pydantic: Optional pydantic model to parse the task output into.

    Returns:
        Task: Initialized Task instance.
    """

    kwargs: dict[str, Any] = {
        "config": config,
        "agent": agent,
    }

    if output_pydantic:
        kwargs["output_pydantic"] = output_pydantic
    if max_retries:
        kwargs["max_retries"] = max_retries

    return Task(**kwargs)


def _load_yaml_config(path: str | Path) -> dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        path: Path to the YAML file.

    Returns:
        dict[str, Any]: Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file cannot be parsed as valid YAML.
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_roadmap_crew(llm: LLM) -> Crew:
    """
    Create the documentation roadmap crew responsible for code analysis and planning documentation roadmap.

    The crew consists of:
    - Codebase Analyst agent: analyzes the codebase using file system tools.
    - Documentation Architect agent: generates a structured documentation roadmap.

    Configuration for agents and tasks is loaded from:
    - ./config/roadmap/agents.yaml
    - ./config/roadmap/tasks.yaml

    Args:
        llm (LLM): Preconfigured LLM instance to be used by all agents.

    Returns:
        Crew: Initialized roadmap crew with inspect codebase architecture and design documentation roadmap tasks.
    """
    # Load configurations for agents and tasks from YAML files
    agents_config = _load_yaml_config(roadmap_agents_config_path)
    tasks_config = _load_yaml_config(roadmap_tasks_config_path)

    # Create agents
    codebase_analyst = _create_agent(config=agents_config["codebase_analyst"], llm=llm)
    documentation_architect = _create_agent(config=agents_config["documentation_architect"], llm=llm)

    # Create tasks
    inspect_codebase_architecture = _create_task(
        config=tasks_config["inspect_codebase_architecture"], agent=codebase_analyst
    )
    design_documentation_roadmap = _create_task(
        config=tasks_config["design_documentation_roadmap"],
        agent=documentation_architect,
        output_pydantic=DocumentationPlan,
    )

    # Create and return the crew
    return Crew(
        agents=[codebase_analyst, documentation_architect],
        tasks=[inspect_codebase_architecture, design_documentation_roadmap],
        verbose=False,
    )


def create_documentation_crew(llm: LLM) -> Crew:
    """
    Create the documentation crew responsible for drafting and reviewing documentation.

    The crew consists of:
    - Tech Documentation Writer agent: produces initial documentation.
    - Documentation Auditor agent: performs audit of generated docs.

    Configuration for agents and tasks is loaded from:
    - ./config/documentation/agents.yaml
    - ./config/documentation/tasks.yaml

    Args:
        llm: Preconfigured LLM instance to be used by the documentation agents.

    Returns:
        Crew: Initialized documentation crew with documentation, validation and finalization tasks.
    """
    # Load agent and task configurations from YAML files
    agents_config = _load_yaml_config(documentation_agents_config_path)
    tasks_config = _load_yaml_config(documentation_tasks_config_path)

    # Create agents
    tech_documentation_writer = _create_agent(config=agents_config["tech_documentation_writer"], llm=llm)
    documentation_auditor = Agent(
        config=agents_config["documentation_auditor"],
        tools=[
            DirectoryReadTool(directory="../documentations/", name="Check documentation folder"),
            FileReadTool(),
        ],
        llm=llm,
    )

    # Create tasks
    author_verified_documentation = _create_task(
        config=tasks_config["author_verified_documentation"], agent=tech_documentation_writer
    )
    validate_and_finalize_documentation = _create_task(
        config=tasks_config["validate_and_finalize_documentation"], agent=documentation_auditor, max_retries=5
    )

    # Create and return the crew
    return Crew(
        agents=[tech_documentation_writer, documentation_auditor],
        tasks=[author_verified_documentation, validate_and_finalize_documentation],
        verbose=False,
    )
