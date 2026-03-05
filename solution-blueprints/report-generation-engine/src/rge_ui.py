# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Streamlit UI for report generation.

Provides an interactive web interface for generating reports with
real-time progress tracking.
"""

import asyncio
import logging
from datetime import datetime

import streamlit as st
from rge_client_factory import create_llm_client, create_tavily_client
from rge_config import get_config
from rge_models import ReportRequest
from rge_report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("rge_ui")

# Page configuration
st.set_page_config(
    page_title="Report Generator",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Title and description
st.title("📄 AI Report Generator")
st.markdown(
    """
Generate comprehensive, well-researched reports on any topic using AI.
The system plans the report structure, conducts web research, and writes
each section with evidence-based content.
"""
)


# Helper function to run async code
def run_async(coro):
    """Run async coroutine in Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


# Load default values from config.yaml
def load_defaults():
    """Load default topic and structure from config.yaml."""
    try:
        config = get_config()
        return {
            "topic": config.default_topic or "",
            "report_structure": config.default_report_structure
            or ("The report should include:\n" "- Introduction\n" "- Main analysis sections\n" "- Conclusion"),
        }
    except Exception as e:
        logger.warning(f"Could not load defaults from config: {e}")
        return {
            "topic": "",
            "report_structure": (
                "The report should include:\n" "- Introduction\n" "- Main analysis sections\n" "- Conclusion"
            ),
        }


defaults = load_defaults()

# Load config for default values
config = get_config()

logger.info("Done - Report Generator UI initialized")

# Input form
with st.form("report_config"):
    st.subheader("📋 Report Configuration")

    topic = st.text_input(
        "Report Topic *",
        value=defaults["topic"],
        placeholder="e.g., Comparison of Python web frameworks",
        help="What should the report be about?",
    )

    report_structure = st.text_area(
        "Report Structure Guidelines *",
        value=defaults["report_structure"],
        height=150,
        help="Describe the desired organization and sections",
    )

    with st.expander("⚙️ Advanced Options"):
        col1, col2 = st.columns(2)

        with col1:
            number_of_queries = st.slider(
                "Queries per section",
                min_value=1,
                max_value=5,
                value=config.number_of_queries,
                help="More queries = more comprehensive research",
            )

            max_section_length = st.slider(
                "Max words per section",
                min_value=100,
                max_value=2000,
                value=config.max_section_length,
                step=100,
                help="Word limit for main content sections",
            )

            final_section_length = st.slider(
                "Max words for intro/conclusion",
                min_value=100,
                max_value=500,
                value=config.final_section_length,
                step=50,
                help="Word limit for introduction and conclusion sections",
            )

        with col2:
            tavily_topic = st.selectbox(
                "Search Type",
                options=["general", "news"],
                index=0 if config.tavily_topic == "general" else 1,
                help="Type of web search to perform",
            )

            tavily_max_results = st.slider(
                "Max results per query",
                min_value=1,
                max_value=10,
                value=config.tavily_max_results,
                help="Maximum search results to use per query",
            )

            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=config.llm_temperature,
                step=0.1,
                help="Generation creativity (0.0=focused, 1.0=creative)",
            )

            tavily_days = None
            if tavily_topic == "news":
                tavily_days = st.slider("Days back (news only)", min_value=1, max_value=30, value=7)

    submitted = st.form_submit_button("🚀 Generate Report", type="primary", use_container_width=True)


# Report generation function
async def run_report_generation(
    topic: str,
    report_structure: str,
    number_of_queries: int,
    tavily_topic: str,
    tavily_days: int | None,
    max_section_length: int,
    tavily_max_results: int,
    final_section_length: int,
    temperature: float,
    progress_container,
    status_placeholder,
    progress_bar,
    log_placeholder,
):
    """
    Run report generation with real-time UI updates.
    Updates the Streamlit UI as progress events are received.
    """

    # Initialize generator (cached in session state)
    if "generator" not in st.session_state:
        with st.spinner("Initializing report generator..."):
            try:
                config = get_config()
                llm = create_llm_client(config)
                tavily = create_tavily_client(config)

                st.session_state.generator = ReportGenerator(llm, tavily, config)
                logger.info("Done - Generator initialized")

            except Exception as e:
                st.error(f"Initialization failed: {e}")
                logger.error(f"Init error: {e}", exc_info=True)
                return ""

    generator = st.session_state.generator

    # Log UI parameters for verification
    logger.info(
        f"UI Parameters - temperature: {temperature}, max_section_length: {max_section_length}, "
        f"final_section_length: {final_section_length}, tavily_max_results: {tavily_max_results}, "
        f"number_of_queries: {number_of_queries}"
    )

    # Create request
    request = ReportRequest(
        topic=topic,
        report_structure=report_structure,
        number_of_queries=number_of_queries,
        tavily_topic=tavily_topic,
        tavily_days=tavily_days,
        max_section_length=max_section_length,
        tavily_max_results=tavily_max_results,
        final_section_length=final_section_length,
        temperature=temperature,
    )

    logger.info("ReportRequest created with custom parameters")

    # Track progress
    progress_log = []
    final_report = ""

    # Generate report with progress updates
    try:
        async for event_type, data in generator.generate_full_report(request):

            if event_type == "status":
                stage = data.get("stage", "")
                message = data.get("message", "")
                progress = data.get("progress", 0)

                # Update progress bar
                progress_bar.progress(progress / 100.0)

                # Update status
                status_placeholder.info(f"**{stage.title()}** - {message}")

                # Add to log
                log_entry = f"[{progress:3d}%] {message}"
                progress_log.append(log_entry)
                log_placeholder.text("\n".join(progress_log[-15:]))  # Last 15 lines

            elif event_type == "sections":
                sections = data.get("sections", [])
                message = data.get("message", "")

                status_placeholder.success(f"✓ {message}")

                # Display section list
                with progress_container:
                    st.write("**Sections to write:**")
                    for section in sections:
                        st.write(f"  • {section['name']}")

            elif event_type == "complete":
                final_report = data.get("final_report", "")
                progress_bar.progress(1.0)
                status_placeholder.success("✅ Report generation complete!")

            elif event_type == "error":
                error_msg = data.get("message", "Unknown error")
                status_placeholder.error(f"❌ Error: {error_msg}")
                break

    except Exception as e:
        status_placeholder.error(f"❌ Exception: {e}")
        logger.error(f"Generation error: {e}", exc_info=True)

    return final_report


# Handle form submission
if submitted:
    # Validation
    if not topic or not report_structure:
        st.error("⚠️ Please fill in both Topic and Report Structure")
    else:
        # Progress section
        st.divider()
        st.subheader("📊 Generation Progress")

        progress_container = st.container()

        with progress_container:
            status_placeholder = st.empty()
            progress_bar = st.progress(0)

            with st.expander("📋 Detailed Log", expanded=True):
                log_placeholder = st.empty()

        # Run generation
        final_report = run_async(
            run_report_generation(
                topic=topic,
                report_structure=report_structure,
                number_of_queries=number_of_queries,
                tavily_topic=tavily_topic,
                tavily_days=tavily_days,
                max_section_length=max_section_length,
                tavily_max_results=tavily_max_results,
                final_section_length=final_section_length,
                temperature=temperature,
                progress_container=progress_container,
                status_placeholder=status_placeholder,
                progress_bar=progress_bar,
                log_placeholder=log_placeholder,
            )
        )

        # Display final report
        if final_report:
            st.divider()
            st.subheader("📄 Final Report")

            # Tabs for different views
            tab1, tab2 = st.tabs(["📖 Rendered", "📝 Markdown"])

            with tab1:
                st.markdown(final_report)

            with tab2:
                st.code(final_report, language="markdown")

            # Download button
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="⬇️ Download Report (Markdown)",
                data=final_report,
                file_name=f"report_{timestamp}.md",
                mime="text/markdown",
                use_container_width=True,
                type="primary",
            )

            # Store in session state for persistence
            st.session_state.last_report = final_report


# Display previous report if exists (page refresh)
elif "last_report" in st.session_state and st.session_state.last_report:
    st.divider()
    st.info("ℹ️ Showing previous report. Generate a new one using the form above.")

    with st.expander("📄 Previous Report", expanded=False):
        st.markdown(st.session_state.last_report)


# Footer
st.divider()
st.caption("Powered by LangChain, AMD, and Tavily Search")
