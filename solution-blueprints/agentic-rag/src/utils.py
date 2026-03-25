# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import hashlib
import html
import logging
import time
from typing import Any, AsyncGenerator, Dict, List

import requests
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader

# This module is the single source of truth for shared utilities, prompt templates,
# and reusable components used across the entire Agentic RAG system.

# LOGGING:


def setup_logging(name: str):
    """Millisecond-precision logging for async TaskGroup debugging."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = setup_logging("utils")

# HEALTH CHECK:


def get_service_health(mcp_url: str) -> bool:
    """Returns True if the MCP server process is reachable."""
    try:
        # Strip /sse to hit the root endpoint; 404 is acceptable (server is up but no route)
        health_url = mcp_url.replace("/sse", "")
        response = requests.get(health_url, timeout=2)
        return response.status_code in [200, 404]
    except Exception:
        return False


# TEXT PROCESSING:

# Common English stop words filtered out during keyword extraction to improve retrieval quality.
# Not exhaustive — the `len(w) > 2` check in extract_key_terms() also filters short words
# like "a", "an", "as", "at", "be", "by", "do", "go", "if", "in", "is", "it", "no", "of",
# "on", "or", "so", "to", "up", "we".
STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "can",
        "will",
        "have",
        "has",
        "had",
        "not",
        "but",
        "that",
        "this",
        "with",
        "from",
        "was",
        "were",
        "been",
        "what",
        "where",
        "when",
        "how",
        "who",
        "why",
        "your",
        "mine",
        "they",
        "them",
        "their",
        "about",
        "which",
        "after",
        "before",
        "each",
        "every",
        "some",
        "than",
        "then",
        "into",
        "also",
        "does",
        "did",
        "its",
        "our",
        "out",
        "would",
        "could",
        "should",
        "these",
        "those",
        "there",
        "here",
        "other",
        "more",
        "most",
        "only",
        "over",
        "such",
        "very",
        "just",
        "any",
        "all",
    }
)


def extract_key_terms(text: str) -> List[str]:
    """
    Extracts deduplicated, meaningful keywords from text.
    Used by the retrieval pipeline for logging and query analysis.
    """
    clean = "".join(c if c.isalnum() else " " for c in text.lower())  # Remove punctuation
    words = clean.split()
    important = [w for w in words if len(w) > 2 and w not in STOP_WORDS]  # Skip short/common words
    return list(dict.fromkeys(important))  # Deduplicate while preserving insertion order


def content_hash(text: str) -> str:
    """MD5 hash of text content — used for chunk deduplication in the DB."""
    return hashlib.md5(text.encode()).hexdigest()


# DOCUMENT LOADING:


def load_docs(file_paths: List[str]) -> List[str]:
    """Load PDF / TXT files into raw text strings."""
    texts = []
    for path in file_paths:
        try:
            loader = PyMuPDFLoader(path) if path.endswith(".pdf") else TextLoader(path)
            content = "\n".join([d.page_content for d in loader.load()])
            texts.append(content)
            logger.info(f"Loaded: {path} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"IO Error on {path}: {e}")
    return texts


# EMBEDDING (reusable across DB backends):


class RemoteEmbeddingFunction:
    """
    Calls an OpenAI-compatible embedding endpoint (e.g. Infinity).
    Implements both the ChromaDB EmbeddingFunction protocol and
    the LangChain Embeddings interface.
    """

    def __init__(self, url: str, model: str):
        self.url = url  # OpenAI-compatible /embeddings endpoint
        self.model = model  # Model name served by the endpoint (e.g. "intfloat/multilingual-e5-large-instruct")

    # ChromaDB protocol — called when Chroma needs to embed documents internally
    def __call__(self, input: List[str]) -> List[List[float]]:
        return self._embed(input)

    # LangChain protocol — called by LangChain's Chroma wrapper during add/search
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]

    def _embed(self, texts: List[str]) -> List[List[float]]:
        from config import BACKOFF_FACTOR, INITIAL_DELAY, MAX_RETRIES

        payload = {"model": self.model, "input": texts}
        delay = INITIAL_DELAY
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(self.url, json=payload, timeout=60)
                resp.raise_for_status()
                return [item["embedding"] for item in resp.json()["data"]]
            except requests.RequestException:
                if attempt == MAX_RETRIES:
                    raise
                logger.warning(
                    "Embedding request failed (attempt %d/%d), retrying in %.1fs", attempt, MAX_RETRIES, delay
                )
                time.sleep(delay)
                delay *= BACKOFF_FACTOR
        raise RuntimeError("Unreachable")


# TIMEOUT CONSTANTS (seconds):

SESSION_INIT_TIMEOUT = 30.0
LLM_REQUEST_TIMEOUT = 60.0
COMPLETENESS_CHECK_TIMEOUT = 10.0
GRADER_TIMEOUT = 15.0
RETRIEVAL_TIMEOUT = 20.0

# TRUNCATION LIMITS (characters):

COMPLETENESS_CONTEXT_LIMIT = 4000
GRADER_TEXT_LIMIT = 8000
GRADER_CHUNK_LIMIT = 2000  # Per-chunk character limit when grading individual passages
FOUND_PREVIEW_LIMIT = 300
RETRIEVAL_PREVIEW_LIMIT = 75


# LLM RESPONSE HELPERS (used by rag_agent.py):


def strip_tool_calls(response) -> None:
    """Remove accidental tool_calls from an LLM response (defensive).

    Sometimes the LLM emits tool_calls alongside a text answer.
    If we don't strip them, LangGraph routes to 'retrieve' instead of END,
    causing an infinite loop.
    """
    if hasattr(response, "tool_calls"):
        response.tool_calls = []
    if hasattr(response, "additional_kwargs") and "tool_calls" in response.additional_kwargs:
        del response.additional_kwargs["tool_calls"]


# UI TRACE FORMATTING:

_TRACE_ICONS = {
    "status": "🤖",
    "retrieval": "🔍",
    "grader": "⚖️",
    "reflection": "🤔",
    "completeness": "📋",
}


def format_trace_event(event_type: str, data: Dict[str, Any]) -> str:
    """Generates HTML chunks for the trace UI. Uses semi-transparent backgrounds for dark mode compatibility."""

    if event_type == "grader":
        is_relevant = data.get("is_relevant", False)
        color = "rgba(76,175,80,0.15)" if is_relevant else "rgba(244,67,54,0.15)"
        border = "#4caf50" if is_relevant else "#f44336"
        label = "Relevant" if is_relevant else "Not Relevant"
        reason = html.escape(str(data.get("reason", "")))
        return (
            f'\n<div style="margin:4px 0;padding:8px;background:{color};'
            f'border-left:3px solid {border};border-radius:4px;">'
            f'<div>{_TRACE_ICONS["grader"]} <b>Assessment:</b> {label}</div>'
            f'<div style="font-size:0.9em;opacity:0.75;margin-top:4px;">{reason}</div>'
            f"</div>\n"
        )

    if event_type == "retrieval":
        query = html.escape(str(data.get("query", "")))
        return (
            f'\n<div style="margin:4px 0;padding:8px;background:rgba(33,150,243,0.15);'
            f'border-left:3px solid #2196f3;border-radius:4px;">'
            f'<div>{_TRACE_ICONS["retrieval"]} <b>Retrieval:</b></div>'
            f'<div style="font-size:0.9em;opacity:0.8;font-family:monospace;">'
            f"{query}</div></div>\n"
        )

    if event_type == "completeness":
        verdict = data.get("verdict", "")
        is_full = verdict == "FULLY"
        color = "rgba(76,175,80,0.15)" if is_full else "rgba(255,152,0,0.15)"
        border = "#4caf50" if is_full else "#ff9800"
        label = "Context is complete" if is_full else "Context is partial — searching for more"
        return (
            f'\n<div style="margin:4px 0;padding:8px;background:{color};'
            f'border-left:3px solid {border};border-radius:4px;">'
            f'<div>{_TRACE_ICONS["completeness"]} <b>Completeness Check:</b> {label}</div>'
            f"</div>\n"
        )

    # Default fallback for status / reflection / other
    raw_msg = data.get("message") or data.get("query") or data.get("suggestion") or str(data)
    msg = html.escape(str(raw_msg))
    return (
        f'\n<div style="margin:4px 0;padding:8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;">'
        f'{_TRACE_ICONS.get(event_type, "•")} {msg}</div>\n'
    )


# STREAM DISPATCH (used by rag_agent.py):


async def stream_agent_events(
    agent_app, initial_input: Dict[str, Any], recursion_limit: int
) -> AsyncGenerator[str, None]:
    """Stream graph execution events, yielding formatted trace strings for the UI.

    Handles both "values" events (state snapshots for tracking search_count)
    and "updates" events (per-node diffs for trace display).
    """
    search_count = 0

    async for mode, event in agent_app.astream(
        initial_input, stream_mode=["updates", "values"], config={"recursion_limit": recursion_limit}
    ):
        if mode == "values":
            search_count = event.get("search_count", 0)
            continue

        if mode == "updates":
            node_name = list(event.keys())[0]
            update_data = event[node_name]

            if node_name == "reasoner":
                # Surface the completeness check verdict if present
                verdict = update_data.get("completeness_verdict", "")
                if verdict:
                    yield format_trace_event(
                        "completeness",
                        {"verdict": verdict},
                    )

                if "messages" in update_data:
                    msg = update_data["messages"][-1]

                    if msg.content and hasattr(msg, "tool_calls") and msg.tool_calls:
                        yield format_trace_event(
                            "reflection", {"suggestion": msg.content, "failed_attempts": search_count}
                        )

                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        yield f"\n**Final Answer:**\n{msg.content}"
                    else:
                        yield format_trace_event(
                            "status", {"message": f"Executing search... (Attempt {search_count + 1})"}
                        )

            elif node_name == "tool_executor":
                if "messages" in update_data:
                    content = update_data["messages"][0].content
                    preview = (
                        (content[:RETRIEVAL_PREVIEW_LIMIT] + "...")
                        if len(content) > RETRIEVAL_PREVIEW_LIMIT
                        else content
                    )
                    yield format_trace_event("retrieval", {"query": f"Fetched {len(content)} chars: {preview}"})

            elif node_name == "grader":
                relevance = update_data.get("relevance", "unknown")
                is_rel = relevance == "yes"
                yield format_trace_event("grader", {"is_relevant": is_rel, "reason": f"Verdict: {relevance.upper()}"})
