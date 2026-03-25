<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic RAG

AI-powered document Q&A system that uses a LangGraph agent with Model Context Protocol (MCP) for modular, tool-based retrieval. The agent interprets user questions, iteratively searches a vector knowledge base via MCP tool calls, grades the retrieved context for relevance, and synthesizes a final answer using an LLM.

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="Agentic RAG consists of 4 components: embedding server for embedding generation, chromadb server for embeddings storage and retrieval, llm server and Gradio UI server for the application itself." src="architecture-diagram-light-scheme.png">
</picture>

The user uploads documents and asks questions through the Gradio web UI. Uploaded documents are chunked and indexed into ChromaDB via the MCP server. For each question, the RAG agent runs a LangGraph loop — reasoning with the LLM, retrieving relevant chunks through MCP tools, grading their relevance, and re-searching if needed — until a complete answer is assembled and streamed back to the UI.

## Key Features

* Document ingestion from PDF and TXT files into a persistent vector knowledge base
* Agentic retrieval loop: reason → search → grade → re-search until fully answered (max 3 searches)
* Relevance grading and deduplication of retrieved chunks before answer synthesis
* MCP-based tool separation: retrieval logic runs in an isolated pod, decoupled from the agent
* Real-time streaming of agent reasoning trace and final answer to the UI
* Connects to the MCP server via SSE transport with automatic tool discovery

## Software

* **LLM Service** - OpenAI-compatible endpoint (AIM vLLM or external), used for reasoning, grading, and answer synthesis
* **MCP Server** - Exposes document tools (`build_knowledge_base`, `retrieve_documents`, `clear_database`, `get_database_stats`) via Model Context Protocol over SSE
* **Gradio UI** - Web interface for uploading documents and asking questions, with live trace output
* **RAG Agent** - LangGraph state machine that orchestrates LLM and MCP interactions
* **Embedding Service** - Infinity server that generates vector embeddings for document chunks and queries
* **ChromaDB** - Persistent vector store used for MMR-based semantic retrieval

## System Requirements

Kubernetes cluster with AMD GPU nodes (GPU count depends on LLM model size)

## Third-party Libraries

| Library | License |
|---------|---------|
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT |
| [LangChain](https://github.com/langchain-ai/langchain) | MIT |
| [MCP (Model Context Protocol)](https://github.com/modelcontextprotocol/python-sdk) | MIT |
| [FastMCP](https://github.com/jlowin/fastmcp) | Apache-2.0 |
| [Gradio](https://github.com/gradio-app/gradio) | Apache-2.0 |
| [ChromaDB](https://github.com/chroma-core/chroma) | Apache-2.0 |
| [Infinity Embedding](https://github.com/michaelfeil/infinity) | MIT |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 |

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit). Third-party components are governed by their respective licenses.
