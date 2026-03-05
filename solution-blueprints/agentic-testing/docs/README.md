<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic Testing

AI-powered UI testing framework that uses an LLM agent with Playwright MCP for browser automation. The agent interprets Gherkin-style Given-When-Then specifications and executes tests via MCP tool calls.

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt=" " src="architecture-diagram-light-scheme.png">
</picture>

The user enters test specifications in Gherkin format (Given-When-Then syntax) through the Streamlit web UI. The UI provides real-time feedback during test execution, displaying live logs and results as the agent interacts with the browser via Playwright MCP.

## Key Features

* Web-based UI for entering Gherkin (Given-When-Then) test specifications
* Real-time test execution logs and progress tracking
* Browser automation via Playwright MCP server (deployed as K8s service)
* Service health monitoring in the UI sidebar
* Connects to MCP server via SSE transport

## Software

* **LLM Service** - OpenAI-compatible endpoint (AIM or external)
* **Playwright MCP Server** - Exposes browser automation tools via Model Context Protocol
* **Streamlit UI** - Web interface for entering Gherkin specs and viewing test results
* **Python Agent** - Orchestrates LLM and MCP interactions using OpenAI SDK

## System Requirements

Kubernetes cluster with GPU nodes (GPU count depends on LLM model size)

## Third-party Libraries

| Library | License |
|---------|---------|
| [Playwright MCP](https://github.com/microsoft/playwright) | Apache-2.0 |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | MIT |

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit). Third-party components are governed by their respective licenses.
