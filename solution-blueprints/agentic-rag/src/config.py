# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import time
import urllib.parse
from typing import Final, cast

import requests

# This module reads all configuration from environment variables.
# Defaults are suitable for in-cluster Kubernetes deployment.
# Override via Helm values.yaml -> ConfigMap -> env vars.

__all__ = [
    "TITLE",
    "GRADIO_PORT",
    "MCP_URL",
    "INFINITY_EMBEDDING_URL",
    "VLLM_BASE_URL",
    "CHROMADB_URL",
    "CHROMADB_HOST",
    "CHROMADB_PORT",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "TOP_K_DOCS",
    "EMBED_MODEL",
    "GEN_MODEL",
    "MAX_RETRIES",
    "INITIAL_DELAY",
    "BACKOFF_FACTOR",
]

TITLE = "Agentic RAG (MCP Architecture)"
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))

# MCP_URL: The SSE endpoint the agent connects to for tool discovery and invocation.
# In K8s, this uses the internal Service DNS name to reach the MCP server.
MCP_URL: Final[str] = cast(str, os.getenv("MCP_URL", "http://localhost:8000/sse"))

# Service endpoints for the three backend components
INFINITY_EMBEDDING_URL = cast(str, os.getenv("EMBEDDING_URL", "http://embedding-e5-large:7997/embeddings"))
VLLM_BASE_URL = cast(str, os.getenv("VLLM_URL", "http://llama-3-3-70b:8000/v1"))

# ChromaDB connection: supports either a full URL or separate host/port
CHROMADB_URL = cast(str, os.getenv("CHROMADB_URL", ""))  # Full URL takes priority if set
CHROMADB_HOST = cast(str, os.getenv("CHROMADB_HOST", "chromadb-store"))  # Fallback: host
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))  # Fallback: port

# Chunking parameters for document splitting
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))  # Max characters per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))  # Overlap between chunks for context continuity
TOP_K_DOCS = int(os.getenv("TOP_K_DOCS", "8"))  # Number of chunks to retrieve per query

# Retry parameters for transient service failures (e.g. embedding calls)
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_DELAY = float(os.getenv("INITIAL_DELAY", "1.0"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "2.0"))

# Number of retries when auto-detecting model names at startup
INIT_RETRIES = int(os.getenv("INIT_RETRIES", "5"))


def init_model(url_suffix: str, base_url: str):
    """Auto-detect the model name served by a backend.

    Queries the /models endpoint (OpenAI-compatible API) to discover
    what model is actually loaded. Falls back to a hardcoded default
    if the service is unreachable after INIT_RETRIES attempts.
    Uses exponential backoff (2^retry seconds) between retries.
    """
    for retry in range(INIT_RETRIES):
        try:
            url = urllib.parse.urljoin(base_url + ("/" if not base_url.endswith("/") else ""), url_suffix)
            r = requests.get(url, timeout=2.0)
            if r.status_code == 200:
                return r.json()["data"][0]["id"]
        except Exception:
            if retry != 0:
                time.sleep(2**retry)
    return None


# Auto-detect model names from the running services.
# If detection fails (service not ready), use sensible defaults.
EMBED_MODEL = (
    init_model("models", INFINITY_EMBEDDING_URL.replace("/embeddings", "/"))
    or "intfloat/multilingual-e5-large-instruct"  # Default embedding model
)
GEN_MODEL = init_model("models", VLLM_BASE_URL) or "openai/gpt-oss-20b"  # Default generation model
