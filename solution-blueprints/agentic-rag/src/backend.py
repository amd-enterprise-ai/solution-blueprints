# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import urllib.parse
from typing import AsyncGenerator, List

import chromadb
import config  # type: ignore[attr-defined]
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils import (  # type: ignore[attr-defined]
    RemoteEmbeddingFunction,
    content_hash,
    extract_key_terms,
    format_trace_event,
    load_docs,
    logger,
)

# This is the only file that contains ChromaDB-specific code.
# To swap to a different vector DB (Pgvector, Pinecone, etc.),
# rewrite this class and update config.py — no other files need changes.


class KnowledgeBase:
    """
    Vector database wrapper. All ChromaDB-specific code lives here.
    To swap DB backends, only this file and config.py need changes.
    """

    def __init__(self):
        self._client = None  # Lazy-initialized ChromaDB HTTP client
        self.vector_store = None  # LangChain Chroma wrapper (also lazy)
        self.collection_name = "rag_collection"  # Single collection for all documents
        self.embedding_function = RemoteEmbeddingFunction(
            url=config.INFINITY_EMBEDDING_URL,  # Infinity embedding server endpoint
            model=config.EMBED_MODEL,  # Model auto-detected at startup
        )

    @property
    def client(self):
        """Lazy-loaded Chroma client with robust URL parsing.
        Supports both CHROMADB_URL (full URL) and CHROMADB_HOST/PORT (split) config."""
        if not self._client:
            if config.CHROMADB_URL:
                parsed = urllib.parse.urlparse(config.CHROMADB_URL)
                self._client = chromadb.HttpClient(
                    host=parsed.hostname,
                    port=parsed.port or 80,
                    ssl=(parsed.scheme == "https"),
                )
            else:
                self._client = chromadb.HttpClient(
                    host=config.CHROMADB_HOST,
                    port=config.CHROMADB_PORT,
                )
        return self._client

    def _get_vector_store(self):
        """Ensures the Chroma vector store connection is active."""
        if self.vector_store is None:
            self.vector_store = Chroma(
                client=self.client,
                collection_name=self.collection_name,
                embedding_function=self.embedding_function,
            )
        return self.vector_store

    def build_from_texts(self, texts: List[str], source_name: str = "default") -> str:
        """Chunk, deduplicate, and upsert texts into the vector store."""
        logger.info(f"--- DB Sync Start | Source: {source_name} ---")

        all_docs = [Document(page_content=t, metadata={"source": source_name}) for t in texts]
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,  # Default: 1000 chars per chunk
            chunk_overlap=config.CHUNK_OVERLAP,  # Default: 200 chars overlap for context continuity
        )
        chunks = splitter.split_documents(all_docs)

        # MD5 deduplication: identical content produces the same ID.
        # Chroma upserts on matching IDs, so re-uploading the same file is a no-op.
        ids = [content_hash(chunk.page_content) for chunk in chunks]

        vs = self._get_vector_store()
        pre_count = vs._collection.count()
        vs.add_documents(documents=chunks, ids=ids)
        post_count = vs._collection.count()
        newly_added = post_count - pre_count

        # Warmup query: forces ChromaDB to finalize its HNSW index immediately after
        # ingestion, so the very first user question doesn't return empty results due
        # to the index not yet being ready.
        try:
            vs.similarity_search("warmup", k=1)
            logger.info("Index warmup complete — HNSW index is ready for queries.")
        except Exception as e:
            logger.warning(f"Index warmup query failed (non-fatal): {e}")

        logger.info(f"Sync Finish | Added: {newly_added} | Total DB Size: {post_count}")
        return f"DB Update: Added {newly_added} new unique chunks. Total DB Size: {post_count}."

    def retrieve(self, query: str, k: int = 0) -> str:
        """MMR (Maximal Marginal Relevance) retrieval with diversity logging.

        MMR balances relevance and diversity to avoid returning near-duplicate chunks.
        - k: number of final results (defaults to config.TOP_K_DOCS, set via TOP_K_DOCS env var)
        - fetch_k=30: initially fetch 30 candidates, then re-rank for diversity
        - lambda_mult=0.7: 70% relevance, 30% diversity (1.0 = pure relevance)
        """
        if k == 0:
            k = config.TOP_K_DOCS
        vs = self._get_vector_store()

        key_terms = extract_key_terms(query)
        safe_query = query.replace("\n", " ").replace("\r", " ")
        logger.info("Retrieval Query: '%s' | Keywords: %s", safe_query, key_terms)

        try:
            docs = vs.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=30,
                lambda_mult=0.7,  # See docstring for parameter explanation
            )
            if docs:
                unique = len(set(d.page_content[:60] for d in docs))
                logger.info(f"📊 MMR Diversity: {unique}/{len(docs)} unique snippets found.")
        except Exception as e:
            logger.error(f"MMR search failed, falling back to similarity: {e}")
            docs = vs.similarity_search(query, k=k)

        if not docs:
            return "No relevant documents found."

        return "\n\n---\n\n".join(f"[Source: {d.metadata.get('source', 'doc')}] {d.page_content}" for d in docs)

    def count(self) -> int:
        """Returns the number of chunks currently in the collection."""
        try:
            return self._get_vector_store()._collection.count()
        except Exception:
            return 0

    def clear(self):
        """Wipes the collection for a fresh session.
        Called before each new file upload to prevent cross-session data leakage."""
        try:
            logger.warning(f"Wiping collection: {self.collection_name}")
            self.client.delete_collection(self.collection_name)
            self.vector_store = None
        except Exception as e:
            logger.error(f"Clear DB failed: {e}")


# Seconds to wait after ChromaDB ingestion before querying, to allow indexing to complete.
CHROMADB_INDEX_DELAY = 3.0


async def ingest_files(session, file_paths: List[str]) -> AsyncGenerator[str, None]:
    """Clear the knowledge base and re-index the given files via MCP.

    Yields status trace events for the UI as each step completes.
    This is the data-sync step that runs before the agent graph starts.
    """
    import asyncio

    try:
        await session.call_tool("clear_database", {})
        yield format_trace_event("status", {"message": "Cleared previous knowledge base."})
    except Exception as e:
        logger.warning(f"Failed to clear database: {e}")

    yield format_trace_event("status", {"message": f"Processing {len(file_paths)} files..."})
    texts = await asyncio.to_thread(load_docs, file_paths)

    if texts:
        yield format_trace_event("status", {"message": "Deduplicating and storing in Knowledge Base..."})
        res = await session.call_tool("build_knowledge_base", {"texts": texts})
        db_info = res.content[0].text
        yield format_trace_event("status", {"message": db_info})
        # Brief pause to let ChromaDB finish indexing before we query it
        await asyncio.sleep(CHROMADB_INDEX_DELAY)
