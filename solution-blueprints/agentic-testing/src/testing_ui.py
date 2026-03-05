# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Streamlit UI for Agentic Testing Blueprint.

This UI provides an interface to:
1. Input GWT (Given-When-Then) specifications
2. Run automated browser tests using Playwright MCP
3. View real-time test execution logs and results
"""

import asyncio

import streamlit as st
from testing_agent import LLM_BASE_URL, MAX_ITERATIONS, MAX_RESULT_LENGTH, MCP_URL, run_tests
from utilities import check_service_ready

# Number of recent log lines to show in live view
MAX_VISIBLE_LINES = 25

# Default GWT specification example
DEFAULT_GWT_SPEC = """@search
Scenario: Search for Ryzen from AMD Wikipedia page
  Given I navigate to "https://en.wikipedia.org/wiki/AMD"
  And the page loads successfully with the search box visible
  When I find the search box in the page header
  And I type "Ryzen" into the search field
  And I submit the search
  Then the browser navigates to a new page
  And the URL contains "/wiki/Ryzen"

@navigation
Scenario: Navigate to History section via Table of Contents
  Given I navigate to "https://en.wikipedia.org/wiki/AMD"
  And the page loads successfully with Table of Contents visible
  When I locate the Table of Contents element
  And I click the entry labeled "History"
  And I wait for anchor navigation to complete
  Then a heading containing "History" is visible in the viewport
"""


async def run_tests_with_ui(
    gwt_specs: str,
    log_placeholder,
    progress_bar,
    max_iterations: int = MAX_ITERATIONS,
    max_result_length: int = MAX_RESULT_LENGTH,
):
    """Run tests asynchronously and update the UI with logs."""
    logs = []
    # Use a counter to generate unique keys for each log update
    log_counter = [0]

    def log(message: str):
        logs.append(message)
        log_counter[0] += 1
        # Show only the most recent lines
        visible_logs = logs[-MAX_VISIBLE_LINES:]
        log_placeholder.text_area(
            "Live test execution output",
            "\n".join(visible_logs),
            height=400,
            disabled=True,
            key=f"live_output_{log_counter[0]}",
        )

    # Run the tests using the agent
    results, pytest_module = await run_tests(
        gwt_specs,
        log_func=log,
        max_iterations=max_iterations,
        max_result_length=max_result_length,
    )

    if progress_bar:
        progress_bar.progress(1.0)

    return logs, results, pytest_module


def main():
    st.set_page_config(
        page_title="Agentic Testing",
        page_icon="🧪",
        layout="wide",
    )

    st.title("🧪 Agentic Testing")
    st.markdown(
        """Automated browser testing using AI agent. The agent interprets your test specifications, interacts with a web application, and reports the results.
    """
    )

    # Service status in sidebar
    with st.sidebar:
        st.header("Service Status")

        llm_status = "🟢 Ready" if LLM_BASE_URL and check_service_ready(f"{LLM_BASE_URL}/models") else "🔴 Not Ready"
        st.write(f"**LLM Service:** {llm_status}")

        mcp_status = "🟢 Ready" if MCP_URL else "🔴 Not Configured"
        st.write(f"**MCP Service:** {mcp_status}")

        st.divider()
        st.header("Configuration")
        max_iterations_input = st.number_input(
            "Max Iterations",
            min_value=1,
            max_value=50,
            value=MAX_ITERATIONS,
            step=1,
            help="Maximum number of tool-calling iterations per scenario",
        )
        max_result_length_input = st.number_input(
            "Max Result Length",
            min_value=1000,
            max_value=50000,
            value=MAX_RESULT_LENGTH,
            step=1000,
            help="Maximum length of tool results before truncation",
        )

        if LLM_BASE_URL:
            st.write(f"**LLM URL:** {LLM_BASE_URL}")
        if MCP_URL:
            st.write(f"**MCP URL:** {MCP_URL}")

    # Main content area
    col1, col2 = st.columns([1, 1])

    with col1:
        gwt_specs = st.text_area(
            "Enter your test scenarios in Gherkin format (Given-When-Then):",
            value=DEFAULT_GWT_SPEC,
            height=400,
            help="Background is auto-added: 'Given a web browser is available via Playwright MCP'. Each scenario needs a unique *@tag* and *Scenario*. Multiple scenarios can be separated by blank lines.",
        )

        run_button = st.button("▶️ Run Tests", type="primary", use_container_width=True)

    with col2:
        if "test_results" not in st.session_state:
            st.session_state.test_results = None
            st.session_state.test_logs = []
            st.session_state.pytest_module = ""
            st.session_state.run_count = 0

        # Log placeholder for live output - use a container to manage the text_area
        log_container = st.empty()

        if run_button:
            if not gwt_specs.strip():
                st.error("Please enter GWT specifications.")
            elif not LLM_BASE_URL:
                st.error("LLM_BASE_URL environment variable is not configured.")
            elif not MCP_URL:
                st.error("MCP_URL environment variable is not configured.")
            else:
                st.session_state.test_logs = []
                st.session_state.test_results = None
                st.session_state.pytest_module = ""
                st.session_state.run_count += 1

                # Run tests asynchronously
                logs, results, pytest_module = asyncio.run(
                    run_tests_with_ui(
                        gwt_specs,
                        log_container,
                        None,
                        max_iterations=max_iterations_input,
                        max_result_length=max_result_length_input,
                    )
                )

                st.session_state.test_logs = logs
                st.session_state.test_results = results
                st.session_state.pytest_module = pytest_module

        # Show stored results in log area if available
        if st.session_state.test_logs and not run_button:
            visible_logs = st.session_state.test_logs[-MAX_VISIBLE_LINES:]
            log_container.text_area(
                "Live test execution output",
                "\n".join(visible_logs),
                height=400,
                disabled=True,
            )

        # Show empty log area if no logs yet
        if not st.session_state.test_logs and not run_button:
            log_container.text_area(
                "Live test execution output",
                "",
                height=400,
                disabled=True,
            )

        # Display summary of results
        if st.session_state.test_results is not None:
            results = st.session_state.test_results
            run_count = getattr(st.session_state, "run_count", 0)
            passed = sum(
                1
                for r in results
                if "pass" in (r["result"] or "").lower() and "fail" not in (r["result"] or "").lower()
            )
            failed = len(results) - passed

            # Collapsible summary with individual results inside
            with st.expander(
                f"**Results:** {len(results)} scenario(s) • ✅ {passed} passed • ❌ {failed} failed", expanded=False
            ):
                for r in results:
                    result_lower = (r["result"] or "").lower()
                    if "pass" in result_lower and "fail" not in result_lower:
                        icon = "✅"
                    elif "fail" in result_lower or r["status"] == "error":
                        icon = "❌"
                    else:
                        icon = "❓"
                    with st.container(border=True):
                        st.markdown(f"**{icon} {r['scenario']}**")
                        st.write(
                            f"Tags: {', '.join(r['tags']) if r['tags'] else 'None'} | Iterations: {r['iterations']}"
                        )
                        st.text_area(
                            "Result",
                            r["result"],
                            height=100,
                            disabled=True,
                            key=f"result_{run_count}_{r['scenario']}",
                            label_visibility="collapsed",
                        )

    # Logs section (collapsible)
    if st.session_state.test_logs:
        run_count = getattr(st.session_state, "run_count", 0)
        with st.expander("📜 Execution Logs", expanded=False):
            logs_text = "\n".join(st.session_state.test_logs)
            st.text_area(
                "Logs",
                logs_text,
                height=400,
                disabled=True,
                key=f"execution_logs_{run_count}",
                label_visibility="collapsed",
            )

    # Generated Pytest Module section
    if hasattr(st.session_state, "pytest_module") and st.session_state.pytest_module:
        st.subheader("🧪 Generated Pytest Module")
        st.markdown(
            "The following pytest-playwright code was generated from the successful test scenarios. "
            "You can download this code to create automated regression tests."
        )
        st.code(st.session_state.pytest_module, language="python", line_numbers=True)

        # Download button
        st.download_button(
            label="📥 Download generated_tests.py",
            data=st.session_state.pytest_module,
            file_name="generated_tests.py",
            mime="text/x-python",
        )


if __name__ == "__main__":
    main()
