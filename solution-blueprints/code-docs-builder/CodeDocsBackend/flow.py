# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

from pipelines import create_documentation_crew, create_roadmap_crew
from state import documentation_status, get_llm_configuration

logger = logging.getLogger("backend")


class CreateDocumentationFlow:
    """
    Orchestrates the end-to-end documentation flow for a single repository.

    The flow consists of:
    - Running the roadmap crew to generate a structured documentation plan.
    - Persisting the plan to disk.
    - Running the documentation crew to generate documentation files for each section.
    - Saving all generated documentation under a per-repository docs directory.

    Attributes:
        repo_id: Unique identifier of the repository.
        repo_path: Path to the local clone of the repository.
        docs_path: Base path where documentation artifacts will be stored.
    """

    def __init__(self, repo_id: str, repo_path: Path, docs_path: Path):
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.docs_path = docs_path

    def run(self):
        """
        Execute the documentation flow for the configured repository.

        Steps:
            1. Run the roadmap crew to generate a documentation plan.
            2. Save the raw plan to `plan.json` under the repository docs directory.
            3. For each planned section, run the documentation crew to generate content.
            4. Save each generated section as an `.mdx` file in the repository docs directory.
        """
        try:
            documentation_status[self.repo_id] = "Waiting for model to initialize..."
            # create llm configuration
            llm_configuration = get_llm_configuration()

            # 1. Generate documentation plan
            logger.info("Step 1/2. Planning documentation roadmap for: %s", self.repo_path)
            repo_name = self.repo_path.__str__().split("/")[-1]
            documentation_status[self.repo_id] = f"Step 1/2. Planning documentation roadmap for: {repo_name}"
            roadmap_crew = create_roadmap_crew(llm=llm_configuration.llm, repo_path=self.repo_path)
            plan = roadmap_crew.kickoff(inputs={"repo_path": str(self.repo_path)})

            titles = "\n".join(f"    - {section.title}" for section in plan.pydantic.sections)
            logger.info("Planned documentation sections for %s:\n%s", self.repo_path, titles)

            # 2. Persist plan to disk
            self._save_plan(self.docs_path, plan.raw)

            # 3. Generate documentation for each section
            documentation_crew = create_documentation_crew(llm=llm_configuration.llm, repo_path=self.repo_path)
            counter = 0
            for section in plan.pydantic.sections:
                logger.info("Step 2/2. Creating documentation for section: %s", section.title)
                documentation_status[self.repo_id] = (
                    f"Step 2/2. Creating documentation for section '{section.title}' (section: {counter + 1}/{len(plan.pydantic.sections)})."
                )
                result = documentation_crew.kickoff(
                    inputs={
                        "repo_path": str(self.repo_path),
                        "title": section.title,
                        "overview": plan.pydantic.overview,
                        "description": section.description,
                        "prerequisites": section.prerequisites,
                        "examples": "\n".join(section.examples),
                        "goal": section.goal,
                    }
                )

                # 4. Save generated documentation to file
                fixed_result = result.raw.replace("|>", "|")
                section_filename = str(counter) + ". " + section.title.lower().replace(" ", "_") + ".mdx"
                counter += 1
                with open(self.docs_path / section_filename, "w", encoding="utf-8") as f:
                    f.write(fixed_result)
            logger.info("Documentation successfully created for: %s", self.repo_path)

            documentation_status[self.repo_id] = "Documentation is ready"
        except Exception as ex:
            logger.exception("Error occurred while generating documentation for repository: %s", self.repo_path)
            documentation_status[self.repo_id] = "Failed"

    def _save_plan(self, project_docs_dir: Path, raw_plan: str) -> None:
        """
        Save the raw documentation plan to a JSON file.

        Args:
            project_docs_dir: Directory where the plan file will be stored.
            raw_plan: Raw plan content returned by the roadmap crew.
        """
        plan_path = project_docs_dir / "plan.json"
        with plan_path.open("w", encoding="utf-8") as plan_file:
            plan_file.write(raw_plan)
