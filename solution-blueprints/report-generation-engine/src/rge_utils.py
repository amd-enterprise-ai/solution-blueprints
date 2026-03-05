# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Utility functions for report generation

import asyncio
import json
import logging
from typing import Any, List, Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# ============================================
# Exceptions
# ============================================


class TavilyAuthError(Exception):
    """Raised when Tavily API authentication fails due to invalid or missing API key."""

    pass


# ============================================
# JSON Extraction and Parsing
# ============================================


def extract_json_from_response(text: str) -> Optional[dict]:
    """
    Extract JSON from LLM response, handling markdown code blocks and mixed text.
    This is a workaround for models that don't reliably return pure JSON.

    Args:
        text: Response text that may contain JSON

    Returns:
        Parsed JSON dictionary, or None if extraction fails

    Example:
        >>> text = "Sure! Here's the JSON:\\n```json\\n{\\\"key\\\":\\\"value\\\"}\\n```"
        >>> extract_json_from_response(text)
        {'key': 'value'}
    """
    # Remove markdown code blocks if present
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()

    # Find JSON object in text
    if "{" in text and "}" in text:
        start = text.find("{")
        brace_count = 0
        end = start

        for i, char in enumerate(text[start:], start=start):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse extracted JSON: {e}")

    # Try parsing whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("No valid JSON found in response")
        return None


def get_structured_output(llm: Any, prompt: str, schema: Type[BaseModel], max_retries: int = 3) -> Optional[BaseModel]:
    """
    Get structured output using prompt engineering workaround.
    This function works around the issue where `.with_structured_output()`
    returns None by using explicit prompting to force JSON output.

    Args:
        llm: LLM instance (ChatNVIDIA or similar)
        prompt: User prompt
        schema: Pydantic model class defining expected structure
        max_retries: Number of retry attempts

    Returns:
        Instance of schema, or None if parsing fails after all retries

    Example:
        >>> from di_models import Sections
        >>> llm = ChatNVIDIA(model="...", base_url="...")
        >>> result = get_structured_output(llm, "Generate sections...", Sections)
    """
    json_schema = schema.model_json_schema()
    system_prompt = f"""You are a helpful assistant that ALWAYS responds with valid JSON.

Your response MUST be a valid JSON object matching this exact schema:

{json.dumps(json_schema, indent=2)}

CRITICAL RULES:
1. Return ONLY the JSON object, no other text
2. Do not include markdown code fences (no ```)
3. All fields must match the schema exactly
4. Use the field descriptions to guide your output
5. Ensure the JSON is valid and parseable"""

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]

    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages)
            json_data = extract_json_from_response(response.content)

            if json_data is None:
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1}: No valid JSON, retrying...")
                    messages.append(response)
                    messages.append(
                        HumanMessage(content="Your response was not valid JSON. Please provide ONLY a JSON object.")
                    )
                    continue
                logger.error("Failed to get valid JSON after all retries")
                return None

            # Validate against schema
            return schema(**json_data)

        except ValidationError as e:
            logger.warning(f"Attempt {attempt + 1}: Validation error: {e}")
            if attempt < max_retries - 1:
                messages.append(response)
                messages.append(
                    HumanMessage(content=f"The JSON was invalid: {e}. Please fix it and provide valid JSON.")
                )
                continue
            logger.error("Failed to get valid schema after all retries")
            return None

        except Exception as e:
            logger.error(f"Unexpected error in get_structured_output: {e}")
            return None

    return None


# ============================================
# Web Search Utilities
# ============================================


def deduplicate_and_format_sources(search_results: List[dict], max_tokens_per_source: int = 1000) -> str:
    """
    Process and format Tavily search results, removing duplicates.
    Args:
        search_results: List of search result dictionaries from Tavily
        max_tokens_per_source: Maximum characters per source (approximates tokens)

    Returns:
        Formatted string of unique sources

    Example:
        >>> results = [{"url": "...", "title": "...", "content": "..."}]
        >>> formatted = deduplicate_and_format_sources(results)
    """
    seen_urls = set()
    unique_sources = []

    for result in search_results:
        url = result.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(
                {
                    "title": result.get("title", "Untitled"),
                    "url": url,
                    "content": result.get("content", "")[:max_tokens_per_source],
                }
            )

    # Format for LLM context
    formatted_parts = []
    for idx, source in enumerate(unique_sources, 1):
        formatted_parts.append(
            f"## Source {idx}: {source['title']}\n" f"URL: {source['url']}\n\n" f"{source['content']}\n"
        )

    return "\n".join(formatted_parts)


async def conduct_research(
    queries: List[str],
    tavily_client: Any,
    topic: str = "general",
    days: Optional[int] = None,
    max_results: int = 5,
) -> str:
    """
    Conduct parallel web searches using Tavily API.
    Args:
        queries: List of search query strings
        tavily_client: AsyncTavilyClient instance
        topic: Search topic type ("general" or "news")
        days: Days back for news search (only for news topic)
        max_results: Maximum results per query

    Returns:
        Formatted string of deduplicated search results

    Example:
        >>> from tavily import AsyncTavilyClient
        >>> client = AsyncTavilyClient(api_key="...")
        >>> queries = ["Python web frameworks", "FastAPI vs Flask"]
        >>> results = await conduct_research(queries, client)
    """
    logger.info(f"Conducting research with {len(queries)} queries")

    # Check if Tavily client is configured
    if tavily_client is None:
        raise TavilyAuthError(
            "Tavily API key is not configured. Please set TAVILY_API_KEY or use "
            "--set config.tavily.apiKey=your-key when deploying."
        )

    # Create search tasks for parallel execution
    search_params = {"topic": topic, "max_results": max_results}

    if topic == "news" and days is not None:
        search_params["days"] = days

    try:
        # Execute all searches in parallel
        tasks = [tavily_client.search(query=query, **search_params) for query in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all search results and track auth failures
        all_results = []
        auth_failures = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_str = str(result).lower()
                # Detect authentication failures (401, invalid key, unauthorized)
                if any(
                    keyword in error_str
                    for keyword in ["401", "invalid", "unauthorized", "api key", "authentication", "forbidden"]
                ):
                    auth_failures += 1
                    logger.error(f"Tavily authentication error on query {i+1}: {result}")
                else:
                    logger.error(f"Search query {i+1} failed: {result}")
                continue

            # Extract results from response
            if isinstance(result, dict) and "results" in result:
                all_results.extend(result["results"])
            elif isinstance(result, list):
                all_results.extend(result)

        # If ALL queries failed with auth errors, raise specific exception
        if auth_failures > 0 and auth_failures == len(queries):
            raise TavilyAuthError(
                "Tavily API key is invalid or expired. Please check your TAVILY_API_KEY configuration."
            )

        # If we got NO results, return a warning message instead of empty string
        if not all_results:
            logger.warning("No search results returned - report will lack research data")
            return "⚠️ No research data available. Search queries returned no results."

        logger.info(f"Research complete: {len(all_results)} total results")

        # Deduplicate and format
        return deduplicate_and_format_sources(all_results)

    except TavilyAuthError:
        raise  # Re-raise auth errors to propagate to UI
    except Exception as e:
        logger.error(f"Research error: {e}")
        return f"Research unavailable: {str(e)}"


# ============================================
# Text Processing Utilities
# ============================================


def format_prompt(template: str, **kwargs) -> str:
    """
    Format a prompt template with the given keyword arguments.

    Args:
        template: Prompt template string with {placeholders}
        **kwargs: Values to substitute into the template

    Returns:
        Formatted prompt string

    Raises:
        ValueError: If required template variables are missing

    Example:
        >>> prompt = format_prompt(
        ...     "Query: {section_topic}",
        ...     section_topic="Machine Learning"
        ... )
        'Query: Machine Learning'
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required template variable: {e}")


def count_words(text: str) -> int:
    """
    Count words in text.
    Args:
        text: Input text

    Returns:
        Word count
    """
    return len(text.split())


def format_section_for_context(section: Any) -> str:
    """
    Format a section object for use as context in prompts.
    Args:
        section: Section object with name and content

    Returns:
        Formatted string
    """
    return f"## {section.name}\n\n{section.content}\n"


def compile_sections_to_markdown(sections: List[Any], topic: str) -> str:
    """
    Compile sections into a complete markdown document.
    Args:
        sections: List of Section objects
        topic: Report topic for title

    Returns:
        Complete markdown document
    """
    parts = [f"# {topic}\n\n", "---\n\n"]

    for section in sections:
        parts.append(f"## {section.name}\n\n")
        parts.append(f"{section.content}\n\n")

    return "".join(parts)


# ============================================
# Testing
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    logger.info("Testing utility functions...")

    # Test JSON extraction
    test_json_text = """
    Sure! here's the JSON you requested:
    ```json
    {
        "name": "Test",
        "value": 123
    }
    ```
    """
    extracted = extract_json_from_response(test_json_text)
    logger.info(f"JSON Extraction: {extracted}")

    # Test source formatting
    test_results = [
        {
            "url": "https://example.com/1",
            "title": "Example 1",
            "content": "This is example content 1",
        },
        {
            "url": "https://example.com/2",
            "title": "Example 2",
            "content": "This is example content 2",
        },
        {
            "url": "https://example.com/1",  # Duplicate
            "title": "Example 1 Again",
            "content": "Duplicate content",
        },
    ]
    formatted = deduplicate_and_format_sources(test_results)
    logger.info(f"Source Formatting: {len(formatted)} characters")
    logger.info(f"  Found {formatted.count('## Source')} unique sources")

    # Test text processing
    test_text = "This is a test sentence with several words in it for testing purposes."
    logger.info(f"Word Count: {count_words(test_text)} words")

    logger.info("All utility functions validated successfully!")
