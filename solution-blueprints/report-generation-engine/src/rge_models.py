# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Pydantic models for data validation and structured output

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


# ============================================
# Report Structure Models
# ============================================


class Section(BaseModel):
    """
    Represents a single section of the report.
    Attributes:
        name: Title of the section
        description: Brief overview of topics to cover
        research: Whether web research is needed for this section
        content: The actual content of the section (populated during writing)
    """

    name: str = Field(description="Name for this section of the report.")
    description: str = Field(
        description="Brief overview of the main topics and concepts to be covered in this section."
    )
    research: bool = Field(description="Whether to perform web research for this section.")
    content: str = Field(default="", description="The actual content of the section.")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "description": self.description,
            "research": self.research,
            "content": self.content,
        }


class Sections(BaseModel):
    """
    Collection of sections for the report structure.
    Attributes:
        sections: List of Section objects
    """

    sections: List[Section] = Field(description="Sections of the report.")


# ============================================
# Search Query Models
# ============================================


class SearchQuery(BaseModel):
    """
    Individual web search query.
    Attributes:
        search_query: The query string to search for
    """

    search_query: str = Field(description="Query for web search.")


class Queries(BaseModel):
    """
    Collection of search queries.
    Attributes:
        queries: List of SearchQuery objects
    """

    queries: List[SearchQuery] = Field(description="List of search queries.")


# ============================================
# API Request/Response Models
# ============================================


class ReportRequest(BaseModel):
    """
    API request model for report generation.
    Attributes:
        topic: Main topic for the report
        report_structure: Guidelines for report organization
        number_of_queries: Number of search queries per section
        tavily_topic: Type of search (general or news)
        tavily_days: Days back for news search (only for news topic)
        max_section_length: Maximum words per section
    """

    topic: str = Field(description="The main topic for the report")
    report_structure: str = Field(description="Guidelines describing the desired report structure")
    number_of_queries: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Number of web search queries to perform per section",
    )
    tavily_topic: Literal["general", "news"] = Field(default="general", description="Type of Tavily search to perform")
    tavily_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Number of days back for news search (only applicable for news topic)",
    )
    max_section_length: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Maximum number of words per section",
    )
    tavily_max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of search results per query",
    )
    final_section_length: int = Field(
        default=300,
        ge=100,
        le=1000,
        description="Maximum number of words for intro/conclusion sections",
    )
    temperature: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="LLM generation temperature (0.0=focused, 1.0=creative)",
    )


class ReportResponse(BaseModel):
    """
    API response model for completed report.
    Attributes:
        topic: Report topic
        sections: List of completed sections
        final_report: Full markdown report
        metadata: Additional information about generation process
    """

    topic: str
    sections: List[Section]
    final_report: str
    metadata: dict = Field(default_factory=dict)


# ============================================
# Workflow State Models (TypedDict for compatibility)
# ============================================


class ReportState(TypedDict):
    """
    State management for report generation workflow.
    Used to track progress through the multi-stage generation process.
    """

    # Input parameters
    topic: str
    tavily_topic: Literal["general", "news"]
    tavily_days: Optional[int]
    report_structure: str
    number_of_queries: int

    # Workflow state
    sections: List[Section]
    completed_sections: List[Section]
    report_sections_from_research: str
    final_report: str


class SectionState(TypedDict):
    """
    State management for individual section processing.
    Used during the research and writing stage for each section.
    """

    tavily_topic: Literal["general", "news"]
    tavily_days: Optional[int]
    number_of_queries: int
    section: Section
    search_queries: List[SearchQuery]
    source_str: str
    completed_section: Section


# ============================================
# Progress Event Models
# ============================================


class ProgressEvent(BaseModel):
    """
    Progress update event for streaming to UI.
    Attributes:
        stage: Current stage of generation
        message: Human-readable status message
        data: Optional data payload
        progress: Progress percentage (0-100)
    """

    stage: Literal[
        "planning",
        "sections_generated",
        "researching",
        "writing",
        "compiling",
        "complete",
        "error",
    ]
    message: str
    data: Optional[dict] = None
    progress: int = Field(ge=0, le=100, default=0)

    def to_ndjson(self) -> str:
        """Convert to NDJSON line for streaming"""
        import json

        return json.dumps(self.model_dump()) + "\n"


# ============================================
# Validation Example
# ============================================

if __name__ == "__main__":
    # Test models
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    logger.info("Testing Pydantic models...")

    # Test Section
    section = Section(
        name="Introduction",
        description="Overview of the topic",
        research=False,
        content="This is the introduction.",
    )
    logger.info(f"Section: {section.name}")
    logger.info(f"  Research required: {section.research}")
    logger.info(f"  Content: {section.content[:50]}...")

    # Test Sections collection
    sections = Sections(sections=[section])
    logger.info(f"Sections: {len(sections.sections)} section(s)")

    # Test SearchQuery
    query = SearchQuery(search_query="machine learning frameworks")
    logger.info(f"SearchQuery: {query.search_query}")

    # Test Queries collection
    queries = Queries(queries=[query])
    logger.info(f"Queries: {len(queries.queries)} query(ies)")

    # Test ReportRequest
    request = ReportRequest(
        topic="Comparison of AI frameworks",
        report_structure="Introduction, Frameworks, Conclusion",
        number_of_queries=2,
        tavily_topic="general",
    )
    logger.info("ReportRequest:")
    logger.info(f"  Topic: {request.topic}")
    logger.info(f"  Queries per section: {request.number_of_queries}")
    logger.info(f"  Search type: {request.tavily_topic}")

    # Test ProgressEvent
    event = ProgressEvent(stage="planning", message="Generating report structure...", progress=10)
    logger.info("ProgressEvent:")
    logger.info(f"  Stage: {event.stage}")
    logger.info(f"  Message: {event.message}")
    logger.info(f"  Progress: {event.progress}%")
    logger.info(f"  NDJSON: {event.to_ndjson()}")

    logger.info("All models validated successfully!")
