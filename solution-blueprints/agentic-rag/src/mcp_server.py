# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import List

import uvicorn
from backend import KnowledgeBase
from mcp.server.fastmcp import FastMCP

from utils import setup_logging  # type: ignore[attr-defined]

# This file defines the MCP (Model Context Protocol) server.
# It exposes tools (build, retrieve, clear, stats) that the agent calls over SSE.
# The agent discovers these tools via the MCP handshake and uses them at runtime.

# Initialize standardized logging
logger = setup_logging("mcp_server")

# 1. INITIALIZE FastMCP
# The name "AgenticRAG-Backend" is sent to the agent during tool discovery.
# The agent sees this name in its available tools list.
mcp = FastMCP("AgenticRAG-Backend")
kb = KnowledgeBase()  # Singleton DB wrapper — shared across all tool calls

# 2. DEFINE TOOLS
# Each @mcp.tool decorator registers a function as a tool the agent can call.
# The description= text is what the LLM reads to decide WHEN to use each tool.
# Clear docstrings act as additional instructions for the LLM.


@mcp.tool(description="Indexes text chunks into the vector database. Use this when new files are uploaded.")
def build_knowledge_base(texts: List[str], source_name: str = "default") -> str:
    """
    Indexes text chunks into the vector database.
    Use this when new files are uploaded or information needs to be stored.
    """
    logger.info(f"MCP Tool Call: [build_knowledge_base] Source: {source_name}")
    try:
        result = kb.build_from_texts(texts, source_name)  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error(f"Failed to build knowledge base: {e}")
        return f"Error: {str(e)}"


@mcp.tool(description="Performs a semantic search to find relevant document snippets to gather facts.")
def retrieve_documents(query: str) -> str:
    """
    Performs a semantic search to find relevant document snippets.
    Use this to gather facts before answering a user's question.
    """
    logger.info(f"MCP Tool Call: [retrieve_documents] Query: {query[:50]}...")
    try:
        context = kb.retrieve(query)
        return context
    except Exception as e:
        logger.error(f"Retrieval tool error: {e}")
        return "Error: Could not access the vector database."


@mcp.tool(description="Wipes all indexed documents. Use this only when a fresh start is requested.")
def clear_database() -> str:
    """
    Wipes all indexed documents. Use this only when a fresh start is requested.
    """
    logger.warning("MCP Tool Call: [clear_database] Wiping collection.")
    try:
        kb.clear()
        return "Database successfully cleared."
    except Exception as e:
        return f"Error clearing database: {str(e)}"


@mcp.tool(description="Returns the current number of chunks in the vector database.")
def get_database_stats() -> str:
    """Returns the total count of documents in the vector store."""
    try:
        count = kb.count()  # type: ignore[attr-defined]
        return f"ChromaDB Status: {count} chunks indexed."
    except Exception:
        return "ChromaDB Status: Empty / Not Initialized"


# 3. MIDDLEWARE FOR K8S COMPATIBILITY
class MCPNetworkMiddleware:
    """
    Ensures that the SSE handshake is not rejected by FastMCP due to
    mismatched Host/Origin headers caused by Kubernetes Service routing.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # K8s internal DNS names (e.g. "knowledge-mcp.default.svc.cluster.local")
            # cause FastMCP's CORS check to reject the connection.
            # We replace Host/Origin with localhost to bypass this check.
            headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() not in (b"host", b"origin")]
            headers.append((b"host", b"localhost:8000"))
            headers.append((b"origin", b"http://localhost:8000"))
            scope["headers"] = headers
        await self.app(scope, receive, send)


# 4. SERVER EXECUTION
if __name__ == "__main__":
    # Create the Starlette/FastAPI app from FastMCP
    app = mcp.sse_app()

    logger.info("Starting Agentic RAG MCP Server on port 8000")

    # We use a 65s keep-alive timeout to stay alive just longer than the Agent's 60s
    # request_timeout. This prevents the SSE session from being torn down mid-request.
    uvicorn.run(
        MCPNetworkMiddleware(app), host="0.0.0.0", port=8000, log_level="info", timeout_keep_alive=65, access_log=True
    )
