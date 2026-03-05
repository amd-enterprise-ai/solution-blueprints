# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Core report generation workflow orchestrator

import logging
from typing import Any, AsyncGenerator, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from rge_config import Config
from rge_models import Queries, ReportRequest, Section, Sections
from rge_utils import (
    TavilyAuthError,
    compile_sections_to_markdown,
    conduct_research,
    count_words,
    format_prompt,
    format_section_for_context,
    get_structured_output,
)
from tavily import AsyncTavilyClient

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Main report generation orchestrator.
    Manages the multi-stage workflow for generating structured reports:
        1. Planning - Generate report outline with sections
        2. Research - Conduct web searches for each section
        3. Writing - Generate content for each section
        4. Compilation - Assemble final report
    """

    def __init__(self, llm: Any, tavily_client: AsyncTavilyClient, config: Config):
        """
        Initialize report generator.
        Args:
            llm: LLM instance
            tavily_client: Async Tavily client for web search
            config: Configuration instance
        """
        self.llm = llm
        self.tavily_client = tavily_client
        self.config = config

    async def generate_report_plan(
        self,
        topic: str,
        report_structure: str,
        number_of_queries: int,
        tavily_topic: str,
        tavily_days: Optional[int],
        tavily_max_results: int,
    ) -> Tuple[List[Section], str]:
        """
        Generate initial report plan with sections.
        This is Stage 1 of the workflow.

        Args:
            topic: Report topic
            report_structure: Structure guidelines
            number_of_queries: Number of planning queries
            tavily_topic: Search type
            tavily_days: Days back for news
            tavily_max_results: Maximum search results per query

        Returns:
            Tuple of (sections list, planning context string)
        """
        logger.info("Stage 1: Generating report plan...")
        # Step 1: Generate planning queries
        query_prompt = format_prompt(
            self.config.prompts["report_planner_query_writer"],
            topic=topic,
            report_organization=report_structure,
            number_of_queries=number_of_queries,
        )

        queries_result = get_structured_output(self.llm, query_prompt, Queries, max_retries=3)

        if not queries_result or not queries_result.queries:
            logger.warning("No planning queries generated, using default")
            query_strings = [f"{topic} overview", f"{topic} comparison"]
        else:
            query_strings = [q.search_query for q in queries_result.queries]
            logger.info("Generated %d planning queries", len(query_strings))

        # Step 2: Research context for planning
        logger.info("Conducting research with max_results: %d", int(tavily_max_results))
        research_context = await conduct_research(
            queries=query_strings,
            tavily_client=self.tavily_client,
            topic=tavily_topic,
            days=tavily_days,
            max_results=tavily_max_results,
        )

        # Step 3: Generate section outline
        outline_prompt = format_prompt(
            self.config.prompts["report_planner"],
            topic=topic,
            report_organization=report_structure,
            context=research_context[:5000],  # Limit context size
        )

        sections_result = get_structured_output(self.llm, outline_prompt, Sections, max_retries=3)

        if not sections_result or not sections_result.sections:
            logger.error("Failed to generate sections")
            raise ValueError("Could not generate report sections")

        logger.info(f"Done - Generated {len(sections_result.sections)} sections")
        return sections_result.sections, research_context

    async def research_section(
        self,
        section: Section,
        number_of_queries: int,
        tavily_topic: str,
        tavily_days: Optional[int],
        tavily_max_results: int,
    ) -> str:
        """
        Research a single section using web search.
        This is part of Stage 2 of the workflow.

        Args:
            section: Section to research
            number_of_queries: Number of search queries
            tavily_topic: Search type
            tavily_days: Days back for news
            tavily_max_results: Maximum search results per query

        Returns:
            Formatted research context string
        """
        logger.info(f"Searching - Researching section: {section.name}")
        # Generate search queries for this section
        query_prompt = format_prompt(
            self.config.prompts["query_writer"],
            section_topic=f"{section.name}: {section.description}",
            number_of_queries=number_of_queries,
        )

        queries_result = get_structured_output(self.llm, query_prompt, Queries, max_retries=3)

        if not queries_result or not queries_result.queries:
            logger.warning(f"No queries for {section.name}, using section name")
            query_strings = [section.name]
        else:
            query_strings = [q.search_query for q in queries_result.queries]

        # Conduct research
        logger.info("Conducting research with max_results: %d", int(tavily_max_results))
        research_context = await conduct_research(
            queries=query_strings,
            tavily_client=self.tavily_client,
            topic=tavily_topic,
            days=tavily_days,
            max_results=tavily_max_results,
        )

        logger.info(f"Done - Research complete for: {section.name}")
        return research_context

    async def write_section(
        self,
        section: Section,
        source_str: str,
        is_final_section: bool = False,
        other_sections_context: str = "",
        max_section_length: int = 1000,
        final_section_length: int = 300,
        temperature: float = 0.6,
    ) -> Section:
        """
        Write section content using LLM.
        This is part of Stage 3 of the workflow.

        Args:
            section: Section to write
            source_str: Research context
            is_final_section: Whether this is intro/conclusion
            other_sections_context: Context from other sections
            max_section_length: Maximum words for regular sections
            final_section_length: Maximum words for intro/conclusion
            temperature: LLM generation temperature

        Returns:
            Section with populated content
        """
        # Choose appropriate prompt based on section type
        if is_final_section and other_sections_context:
            # Use context from other sections for intro/conclusion
            logger.info("Writing final section '%s' with word limit: %d", section.name, int(final_section_length))
            write_prompt = format_prompt(
                self.config.prompts["final_section_writer"],
                section_topic=f"{section.name}: {section.description}",
                context=other_sections_context[:8000],
                final_section_length=final_section_length,
            )
        else:
            # Use research context for main sections
            logger.info("Writing section '%s' with word limit: %d", section.name, int(max_section_length))
            write_prompt = format_prompt(
                self.config.prompts["section_writer"],
                section_topic=f"{section.name}: {section.description}",
                context=source_str[:8000],
                max_section_length=max_section_length,
            )

        # Generate content
        try:
            logger.info("Invoking LLM with temperature: %.1f", float(temperature))
            response = self.llm.invoke(
                [
                    SystemMessage(content="You are an expert technical writer."),
                    HumanMessage(content=write_prompt),
                ],
                temperature=temperature,
            )
            logger.debug(f"LLM response length: {len(response.content)} characters")

            # Clean up duplicate section titles
            content = response.content.strip()

            # Remove section title if LLM included it (## Section Name)
            lines = content.split("\n")
            if lines and lines[0].startswith("## "):
                # Check if the title matches the section name
                title_in_content = lines[0].replace("## ", "").strip()
                if title_in_content.lower() == section.name.lower():
                    # Remove the duplicate title
                    content = "\n".join(lines[1:]).strip()

            # Also remove # title for introduction sections
            if lines and lines[0].startswith("# "):
                content = "\n".join(lines[1:]).strip()

            section.content = content
            word_count = count_words(content)
            word_limit = final_section_length if is_final_section else max_section_length
            logger.info(
                "Done - Section written: %s (%d words, limit: %d)", section.name, int(word_count), int(word_limit)
            )

        except Exception as e:
            logger.error(f"Error writing section {section.name}: {e}")
            section.content = "*Content generation failed for this section.*"

        return section

    async def generate_full_report(self, request: ReportRequest) -> AsyncGenerator[Tuple[str, Any], None]:
        """
        Main workflow: orchestrates all stages.
        Yields progress updates at each step for streaming to UI.

        Args:
            request: Report generation request

        Yields:
            Tuples of (event_type, data) for streaming progress
        """
        # Log all request parameters for verification
        logger.info("=== Report Generation Started ===")
        logger.info("Topic: %s", request.topic.replace("\n", " ").replace("\r", " "))
        logger.info("temperature: %.1f", float(request.temperature))
        logger.info("number_of_queries: %d", int(request.number_of_queries))
        logger.info("max_section_length: %d", int(request.max_section_length))
        logger.info("final_section_length: %d", int(request.final_section_length))
        logger.info("tavily_max_results: %d", int(request.tavily_max_results))
        logger.info("=================================")

        try:
            # Stage 1: Planning
            yield (
                "status",
                {
                    "stage": "planning",
                    "message": "Generating report structure...",
                    "progress": 5,
                },
            )

            sections, planning_context = await self.generate_report_plan(
                topic=request.topic,
                report_structure=request.report_structure,
                number_of_queries=request.number_of_queries,
                tavily_topic=request.tavily_topic,
                tavily_days=request.tavily_days,
                tavily_max_results=request.tavily_max_results,
            )

            yield (
                "sections",
                {
                    "sections": [s.to_dict() for s in sections],
                    "message": f"Generated {len(sections)} sections",
                    "progress": 15,
                },
            )

            # Stage 2 & 3: Research and write each section
            completed_sections = []
            sections_needing_research = [s for s in sections if s.research]
            sections_no_research = [s for s in sections if not s.research]

            # Log research status for visibility
            research_names = [s.name for s in sections_needing_research]
            no_research_names = [s.name for s in sections_no_research]
            logger.info(f"Sections requiring web research ({len(research_names)}): {research_names}")
            logger.info(f"Sections without research ({len(no_research_names)}): {no_research_names}")

            yield (
                "status",
                {
                    "stage": "research_plan",
                    "message": f"Web research: {len(sections_needing_research)} sections, Skip: {len(sections_no_research)} sections",
                    "progress": 18,
                },
            )

            total_sections = len(sections)
            base_progress = 15

            # Process sections that need research
            for idx, section in enumerate(sections_needing_research):
                section_progress = base_progress + int((idx / total_sections) * 70)

                # Research
                yield (
                    "status",
                    {
                        "stage": "researching",
                        "message": f"Researching: {section.name}",
                        "section": section.name,
                        "progress": section_progress,
                    },
                )

                research_context = await self.research_section(
                    section=section,
                    number_of_queries=request.number_of_queries,
                    tavily_topic=request.tavily_topic,
                    tavily_days=request.tavily_days,
                    tavily_max_results=request.tavily_max_results,
                )

                # Write
                yield (
                    "status",
                    {
                        "stage": "writing",
                        "message": f"Writing: {section.name}",
                        "section": section.name,
                        "progress": section_progress + 5,
                    },
                )

                completed_section = await self.write_section(
                    section=section,
                    source_str=research_context,
                    max_section_length=request.max_section_length,
                    temperature=request.temperature,
                )

                completed_sections.append(completed_section)

            # Stage 4: Write final sections (intro/conclusion)
            if sections_no_research:
                # Build context from completed sections
                context_parts = [format_section_for_context(s) for s in completed_sections]
                other_sections_context = "\n\n".join(context_parts)

                # Progress values for final sections: 85, 89, 91, 93
                final_progress_values = [85, 89, 91, 93]
                for idx, section in enumerate(sections_no_research):
                    yield (
                        "status",
                        {
                            "stage": "writing",
                            "message": f"Writing: {section.name}",
                            "section": section.name,
                            "progress": final_progress_values[idx] if idx < 4 else 93,
                        },
                    )

                    completed_section = await self.write_section(
                        section=section,
                        source_str="",
                        is_final_section=True,
                        other_sections_context=other_sections_context,
                        final_section_length=request.final_section_length,
                        temperature=request.temperature,
                    )

                    completed_sections.append(completed_section)

            # Stage 5: Compile final report
            yield (
                "status",
                {
                    "stage": "compiling",
                    "message": "Compiling final report...",
                    "progress": 95,
                },
            )

            # Sort sections to match original order
            section_order = {s.name: i for i, s in enumerate(sections)}
            completed_sections.sort(key=lambda s: section_order.get(s.name, 999))

            final_report = compile_sections_to_markdown(sections=completed_sections, topic=request.topic)

            # Final status before complete
            yield (
                "status",
                {
                    "stage": "complete",
                    "message": "Report generation complete!",
                    "progress": 100,
                },
            )

            # Complete
            yield (
                "complete",
                {
                    "final_report": final_report,
                    "sections": [s.to_dict() for s in completed_sections],
                    "progress": 100,
                },
            )

            logger.info("Done - Report generation complete!")

        except TavilyAuthError as e:
            logger.error(f"Tavily API authentication failed: {e}")
            yield ("error", {"message": str(e), "stage": "research"})
        except Exception as e:
            logger.error(f"Report generation error: {e}", exc_info=True)
            yield ("error", {"message": str(e), "stage": "generation"})
