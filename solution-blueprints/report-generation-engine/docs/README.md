<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Report Generation Engine

This report generation engine blueprint illustrates how automated technical report generation can be implemented using AIMs. It employs a multi-stage LLM workflow with integrated web research — where the system plans, researches, writes, and compiles content — to produce comprehensive, evidence-based technical documents on any topic.

This blueprint follows a four-stage pipeline: Planning generates search queries and creates a section outline, Research conducts parallel web searches via Tavily API, Writing generates content for each section using the gathered research, and Compilation assembles the final markdown report with introduction and conclusion.

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The report generation is performed by a four-stage pipeline with LLM and web research integration." src="architecture-diagram-light-scheme.png">
</picture>

## Key Features

* The report generation engine generates comprehensive technical reports on any user-provided topic.
* Users can customize the report structure or use intelligent defaults.
* Real-time progress tracking shows each stage of the generation process.
* Web research results are automatically integrated and cited in the final report.

## Software

 AIM Solution Blueprints are Kubernetes applications packaged with [Helm](https://helm.sh/). It takes one click to launch them in an AMD Enterprise AI cluster and test them out.

 This blueprint primarily uses the following components:

* AIMs - Large enough model for technical writing and synthesis.
    * Default in this blueprint is Llama-3.3-70b
* Streamlit - provides the web-based user interface.
* FastAPI - provides the REST API backend.
* LangChain - orchestration of LLM calls.
* Tavily API - web search for research integration.

## System Requirements

Kubernetes cluster with AMD GPU nodes (exact number of GPUs depends on AIM LLM)

## Third-party Code and Libraries

* Tavily API: Web search API for research integration
    * Website: https://tavily.com
    * Terms of Use: https://tavily.com/terms-of-service
    * License: Commercial API service; requires API key

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
