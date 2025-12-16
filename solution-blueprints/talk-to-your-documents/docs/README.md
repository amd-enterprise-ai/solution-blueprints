<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Talk to your documents

This blueprint deploys a Retrieval-Augmented Generation (RAG) application which allows you to talk to your documents. It uses a vector database (ChromaDB) to store document embeddings and a large language model (LLM) to answer questions based on the retrieved context.


## Architecture diagram

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="Talk to your documents consists of 4 components: embedding server for embedding generation, chromadb server for embeddings storage and retrieval, llm server and Gradio UI server for the application itself." src="architecture-diagram-light-scheme.png">
</picture>

- **Talk to your documents UI**: The user interface for interacting with the RAG.
- **AIM LLM**: A full, optimized LLM deployment. See the [application chart](../../../aimcharts/aimchart-llm/README.md) for its documentation.
- **Embedding model**: An Infinity server deployment that hosts embedding model to generate embeddings for documents. See the [application chart](../../../aimcharts/aimchart-embedding/README.md) for its documentation.
- **ChromaDB vector store**: A deployment with ChromaDB vector database to store document embeddings. See the [application chart](../../../aimcharts/aimchart-chromadb/README.md) for its documentation.


## Key Features

* **Document-Based Q&A**: Supports uploading multiple documents (PDF and TXT) to build a knowledge base for context-aware answering.


## What's included?

AIM Solution Blueprints are Kubernetes applications packaged with [Helm](https://helm.sh/). It takes one click to launch them in an AMD Enterprise AI cluster and test them out.


### Software Used in This Blueprint
- AIM (Any LLM)
- Any model supported by [infinity](https://github.com/michaelfeil/infinity)
- chromadb
- Gradio

## System Requirements
Kubernetes cluster with AMD GPU nodes (exact number of GPUs depends on AIM LLM)

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
