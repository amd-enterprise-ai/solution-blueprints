# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Agent logic for Agentic Testing Blueprint.

This module contains the core agent functionality for running GWT test scenarios
using Playwright MCP and LLM-based test execution.
"""

import json
import os
import re
from typing import Callable

from gherkin import Scenario, parse_gherkin
from openai import AsyncOpenAI, OpenAI
from testing_prompts import (
    PYTEST_GENERATION_PROMPT_TEMPLATE,
    PYTEST_GENERATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TASK_PROMPT_TEMPLATE,
)
from utilities import clean_tool_name, extract_playwright_code, fetch_model_name, strip_copyright_header

# Configuration from environment
MCP_URL = os.getenv("MCP_URL")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "20"))
MAX_RESULT_LENGTH = int(os.getenv("MAX_RESULT_LENGTH", "15000"))

# SSE client timeout settings (seconds)
# SSE_CONNECT_TIMEOUT: Time to wait for initial SSE connection
# SSE_READ_TIMEOUT: Time to wait for SSE messages during long-running operations
SSE_CONNECT_TIMEOUT = int(os.getenv("SSE_CONNECT_TIMEOUT", "10"))
SSE_READ_TIMEOUT = int(os.getenv("SSE_READ_TIMEOUT", "120"))

# Log separator width (fits typical UI text area without wrapping)
LOG_SEPARATOR = "=" * 55

# Background that is automatically prepended to all scenarios
DEFAULT_BACKGROUND = """Background:
  Given a web browser is available via Playwright MCP
"""


def generate_pytest_with_llm(feature_name: str, results: list[dict], model_name: str) -> str:
    """Use LLM to generate a pytest-playwright module from execution results."""
    # Only include successfully completed scenarios
    successful_results = [r for r in results if r["status"] == "completed"]

    if not successful_results:
        return ""

    # Build context for the LLM
    scenarios_info = []
    for r in successful_results:
        scenario_data = {
            "name": r["scenario"],
            "tags": r.get("tags", []),
            "steps": r.get("steps", ""),
            "playwright_code": r.get("playwright_code", []),
        }
        scenarios_info.append(scenario_data)

    prompt = PYTEST_GENERATION_PROMPT_TEMPLATE.format(
        feature_name=feature_name,
        scenarios_json=json.dumps(scenarios_info, indent=2),
    )

    client = OpenAI(base_url=LLM_BASE_URL, api_key="empty")

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": PYTEST_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    result = response.choices[0].message.content or ""

    # Clean up markdown fences if present
    result = re.sub(r"^```python\n?", "", result)
    result = re.sub(r"\n?```$", "", result)

    return result


async def run_single_scenario(
    scenario: Scenario,
    background: str,
    client: AsyncOpenAI,
    model_name: str,
    log_func: Callable[[str], None],
    max_iters: int,
    max_result_len: int,
) -> dict:
    """Run a single test scenario with its own fresh MCP session.

    Each scenario gets its own MCP connection to ensure complete cleanup
    between scenarios and prevent SSE client state leakage.
    """
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    log_func(f"\n{'=' * 70}")
    log_func(f"SCENARIO: {scenario.name}")
    log_func(f"Tags: {scenario.tags}")
    log_func(LOG_SEPARATOR)

    task = TASK_PROMPT_TEMPLATE.format(
        scenario_name=scenario.name,
        background=background,
        steps=scenario.steps,
    )

    log_func(f"Connecting to MCP at {MCP_URL}")

    try:
        async with sse_client(url=MCP_URL, timeout=SSE_CONNECT_TIMEOUT, sse_read_timeout=SSE_READ_TIMEOUT) as streams:
            async with ClientSession(*streams) as mcp_session:
                await mcp_session.initialize()

                # Get tools from MCP
                result = await mcp_session.list_tools()
                tools = []
                excluded_tools = {"browser_run_code"}
                for t in result.tools:
                    if t.name in excluded_tools:
                        continue
                    tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description or "",
                                "parameters": t.inputSchema or {},
                            },
                        }
                    )

                log_func(f"Loaded {len(tools)} tools from Playwright MCP")
                log_func("\nAvailable tools:")
                for t in result.tools:
                    if t.name not in excluded_tools:
                        desc = t.description or "No description"
                        log_func(f"  - {t.name}: {desc[:80]}..." if len(desc) > 80 else f"  - {t.name}: {desc}")
                log_func("")

                messages: list[dict[str, object]] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": task},
                ]

                playwright_code: list[str] = []
                consecutive_no_tool_calls = 0

                for iteration in range(max_iters):
                    log_func(f"\n=== Iteration {iteration + 1} ===")

                    tool_choice = "required" if consecutive_no_tool_calls >= 2 else "auto"

                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                    )

                    msg = response.choices[0].message

                    if not msg.tool_calls:
                        consecutive_no_tool_calls += 1
                        result_text = msg.content or ""
                        log_func(f"\nAgent response (no tool call):\n{result_text[:500]}...")
                        messages.append({"role": "assistant", "content": result_text})

                        result_lower = result_text.lower()
                        if "pass" in result_lower or "fail" in result_lower:
                            # Close browser before returning to ensure clean state
                            try:
                                await mcp_session.call_tool("browser_close", {})
                                log_func("Browser closed for scenario cleanup")
                            except Exception:
                                pass  # Ignore errors during cleanup
                            return {
                                "scenario": scenario.name,
                                "tags": scenario.tags,
                                "steps": scenario.steps,
                                "result": result_text,
                                "iterations": iteration + 1,
                                "status": "completed",
                                "playwright_code": playwright_code,
                            }

                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You must use a browser tool to continue. "
                                    "Call browser_snapshot to see the current page state."
                                ),
                            }
                        )
                        continue

                    consecutive_no_tool_calls = 0

                    messages.append(
                        {
                            "role": "assistant",
                            "content": msg.content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                                }
                                for tc in msg.tool_calls
                            ],
                        }
                    )

                    for tc in msg.tool_calls:
                        tool_name = clean_tool_name(tc.function.name)
                        log_func(f"\nTool: {tool_name}")
                        log_func(f"Args: {tc.function.arguments}")

                        try:
                            args = json.loads(tc.function.arguments)
                            result = await mcp_session.call_tool(tool_name, args)
                            tool_result = result.content[0].text if result.content else str(result)

                            pw_code = extract_playwright_code(tool_result)
                            if pw_code:
                                playwright_code.append(pw_code)

                            if len(tool_result) > max_result_len:
                                tool_result = tool_result[:max_result_len] + "\n\n[... truncated ...]"
                            display = tool_result[:1000] + "..." if len(tool_result) > 1000 else tool_result
                            log_func(f"Result: {display}")
                        except Exception as e:
                            tool_result = f"Error: {str(e)}"
                            log_func(f"Error: {e}")

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_result,
                            }
                        )

                # Max iterations reached
                log_func("\nMax iterations reached, requesting verdict...")
                messages.append(
                    {
                        "role": "user",
                        "content": "Max iterations reached. Provide your final verdict: PASS or FAIL with evidence.",
                    }
                )
                final_response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="none",
                )
                result_text = final_response.choices[0].message.content or "No verdict provided"
                log_func(f"\nFinal verdict:\n{result_text}")

                # Close browser before returning to ensure clean state
                try:
                    await mcp_session.call_tool("browser_close", {})
                    log_func("Browser closed for scenario cleanup")
                except Exception:
                    pass  # Ignore errors during cleanup

                return {
                    "scenario": scenario.name,
                    "tags": scenario.tags,
                    "steps": scenario.steps,
                    "result": result_text,
                    "iterations": max_iters,
                    "status": "completed",
                    "playwright_code": playwright_code,
                }

    except ExceptionGroup as eg:
        # TaskGroup wraps errors in ExceptionGroup - extract the actual error
        actual_errors = [str(e) for e in eg.exceptions]
        error_summary = "; ".join(actual_errors)
        log_func(f"ERROR: TaskGroup error with {len(eg.exceptions)} sub-exception(s)")
        for i, sub_err in enumerate(eg.exceptions, 1):
            log_func(f"  {i}. {type(sub_err).__name__}: {sub_err}")
        return {
            "scenario": scenario.name,
            "tags": scenario.tags,
            "steps": scenario.steps,
            "result": f"MCP connection failed: {error_summary}",
            "iterations": 0,
            "status": "error",
            "playwright_code": [],
        }

    except Exception as e:
        error_msg = str(e)
        log_func(f"ERROR: {type(e).__name__}: {error_msg}")
        return {
            "scenario": scenario.name,
            "tags": scenario.tags,
            "steps": scenario.steps,
            "result": f"Error: {error_msg}",
            "iterations": 0,
            "status": "error",
            "playwright_code": [],
        }


async def run_tests(
    gwt_specs: str,
    log_func: Callable[[str], None],
    max_iterations: int = MAX_ITERATIONS,
    max_result_length: int = MAX_RESULT_LENGTH,
) -> tuple[list[dict], str]:
    """Run tests asynchronously and return results.

    Args:
        gwt_specs: GWT specifications in Gherkin format.
        log_func: Callback function for logging messages.
        max_iterations: Maximum number of tool-calling iterations per scenario.
        max_result_length: Maximum length of tool results before truncation.

    Returns:
        A tuple of (results list, pytest_module string).
    """
    # Parse GWT specifications - prepend default background if not present
    gwt_specs = strip_copyright_header(gwt_specs)
    if not gwt_specs.strip().startswith("Background:"):
        gwt_specs = DEFAULT_BACKGROUND + "\n" + gwt_specs
    feature = parse_gherkin(gwt_specs)

    # Validate that we have scenarios to run
    if not feature.scenarios:
        log_func(LOG_SEPARATOR)
        log_func("ERROR: No valid scenarios found in input.")
        log_func("")
        log_func("Expected Gherkin format:")
        log_func("  @tag")
        log_func("  Scenario: Description of the test")
        log_func("    Given some precondition")
        log_func("    When some action is performed")
        log_func("    Then some result is expected")
        log_func("")
        log_func("Each scenario needs a unique @tag and a 'Scenario:' line.")
        log_func(LOG_SEPARATOR)
        return [], ""

    # Validate each scenario has proper GWT structure
    invalid_scenarios = []
    for s in feature.scenarios:
        steps_lower = s.steps.lower()
        has_when = "when " in steps_lower or "\nwhen " in steps_lower
        has_then = "then " in steps_lower or "\nthen " in steps_lower
        if not has_when or not has_then:
            invalid_scenarios.append(s.name)

    if invalid_scenarios:
        log_func(LOG_SEPARATOR)
        log_func("ERROR: Invalid scenario structure detected.")
        log_func("")
        log_func("The following scenarios are missing 'When' or 'Then' clauses:")
        for name in invalid_scenarios:
            log_func(f"  - {name}")
        log_func("")
        log_func("Each scenario must have:")
        log_func("  - Given: preconditions (optional)")
        log_func("  - When: the action being tested (required)")
        log_func("  - Then: the expected outcome (required)")
        log_func(LOG_SEPARATOR)
        return [], ""

    log_func(LOG_SEPARATOR)
    log_func(f"FEATURE: {feature.name}")
    log_func(f"Description: {feature.description}")
    log_func(f"Background: {feature.background}")
    log_func(f"Scenarios: {len(feature.scenarios)}")
    for i, s in enumerate(feature.scenarios, 1):
        log_func(f"  {i}. {s.name} (tags: {s.tags})")
    log_func(LOG_SEPARATOR)

    # Fetch model name
    log_func(">>> Fetching model name from LLM service...")
    if not LLM_BASE_URL:
        log_func("ERROR: LLM_BASE_URL not configured")
        return [], ""
    model_name = fetch_model_name(LLM_BASE_URL)
    if not model_name:
        log_func("ERROR: Failed to fetch model name from LLM service")
        return [], ""

    log_func(f"Using model: {model_name}")

    # Create async OpenAI client
    client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key="empty")

    results = []
    total_scenarios = len(feature.scenarios)

    for idx, scenario in enumerate(feature.scenarios):
        log_func(f"\n>>> Running scenario {idx + 1}/{total_scenarios}: {scenario.name}")

        # Run scenario in separate function for complete async context cleanup
        result = await run_single_scenario(
            scenario, feature.background, client, model_name, log_func, max_iterations, max_result_length
        )
        results.append(result)

    log_func("\n>>> Test run complete!")

    # Print summary
    log_func("\n" + LOG_SEPARATOR)
    log_func("TEST RUN SUMMARY")
    log_func(LOG_SEPARATOR)
    log_func(f"Feature: {feature.name}")
    log_func(f"Total Scenarios: {len(results)}")

    passed = 0
    failed = 0
    for r in results:
        result_str = str(r["result"]) if r["result"] else ""
        result_lower = result_str.lower()
        if "pass" in result_lower and "fail" not in result_lower:
            status = "✅ PASS"
            passed += 1
        elif "fail" in result_lower:
            status = "❌ FAIL"
            failed += 1
        elif r["status"] == "error":
            status = "⚠️ ERROR"
            failed += 1
        else:
            status = "❓ UNKNOWN"

        log_func(f"\n{status}: {r['scenario']}")
        log_func(f"  Tags: {r['tags']}")
        log_func(f"  Iterations: {r['iterations']}")
        result_text = result_str or "(no result)"
        log_func(f"  Result: {result_text[:200]}..." if len(result_text) > 200 else f"  Result: {result_text}")

    log_func("\n" + "-" * 70)
    log_func(f"PASSED: {passed}/{len(results)}")
    log_func(f"FAILED: {failed}/{len(results)}")
    log_func(LOG_SEPARATOR)

    # Generate pytest module using LLM (only for successful scenarios)
    pytest_module = ""
    successful_count = sum(1 for r in results if r["status"] == "completed")
    if successful_count > 0:
        log_func("\n" + LOG_SEPARATOR)
        log_func(f"GENERATING PYTEST MODULE ({successful_count} successful scenario(s))...")
        log_func(LOG_SEPARATOR)

        log_func(">>> Calling LLM to generate pytest code...")
        pytest_module = generate_pytest_with_llm(feature.name, results, model_name)

        if pytest_module.strip():
            log_func("\nPytest module generated successfully!")
        else:
            log_func("\nNo pytest module generated")
    else:
        log_func("\n" + LOG_SEPARATOR)
        log_func("SKIPPING PYTEST GENERATION (no successful scenarios)")
        log_func(LOG_SEPARATOR)

    return results, pytest_module
