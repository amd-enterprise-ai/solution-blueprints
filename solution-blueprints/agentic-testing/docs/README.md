<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic Testing
The agentic testing agent, also called quality assurance (QA) agent, is an intelligent system designed to automate the process of testing, verifying, and validating software, data, or content. These agents are becoming more common in modern AI and MLOps pipelines, as well as in software testing. For example, it can run unit tests, integration tests, or end-to-end tests against an application. Or be integrated into CI/CD pipelines to auto-check every new commit or model deployment.

This blueprint uses a specification logic called Given–When–Then which is a powerful way to describe behavioural test scenarios. This structure makes test cases readable to both developers and non-technical stakeholders (like QA or product managers). This blueprint tests login functionalities on a webpage using single shot test generation.

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt=" " src="4148655_AIMs_Blueprints_Diagrams_V2_Blk_Lines_FNL.png">
</picture>

The user enters test specifications on the Given-Then-When format in a .txt file. The output test results are logged, and the generated Python test code is displayed in the job logs (viewable with `kubectl logs job/agentictesting-<name>-job --follow`).

## Key Features

* Single-shot test generation: The agent writes tests based on available MCP tools without interactive webpage exploration.
* Automatically generates Python test scripts from Given-When-Then specifications.
* Additional tests can be easily added in text format within the specification file.
* Comprehensive test results with JSON output and human-readable summaries.

## Software

AIM Solution Blueprints are Kubernetes applications packaged with [Helm](https://helm.sh/). It takes one click to launch them in an AMD Enterprise AI cluster and test them out.

This blueprint primarily uses the following components:

* AIMs - Large enough model for test code generation and execution.
    * Default in this blueprint is Llama-3.3-70b
* Pydantic AI - AI agent framework with MCP support for test generation.
* Playwright MCP Server - Model Context Protocol server that provides browser automation tools to the AI model for web testing.

## System Requirements

Kubernetes cluster with AMD GPU nodes (exact number of GPUs depends on AIM LLM)

## Third-party Code and Libraries

* Pydantic AI: Modern Python agent framework
    * Original source: https://github.com/pydantic/pydantic-ai
    * License: MIT
* Playwright MCP Server: Browser automation via Model Context Protocol
    * Original source: https://github.com/microsoft/playwright
    * License: Apache-2.0

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
