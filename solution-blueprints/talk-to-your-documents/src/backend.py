# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import threading
import urllib.parse
from typing import List

import chromadb
import config
import requests
from chromadb.errors import NotFoundError
from langchain.embeddings.base import Embeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def _make_splitter() -> RecursiveCharacterTextSplitter:
    """Build a splitter that respects the embedding model's max token length.

    When the tokenizer is available, chunk_size/overlap are treated as tokens.
    Otherwise we fall back to characters with a 2x multiplier - conservative
    enough for dense scripts (CJK, Arabic) where 1 token ~ 1 char.
    """
    tok = config.get_embed_tokenizer()
    if tok is not None:
        return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=tok,
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE * 2,
        chunk_overlap=config.CHUNK_OVERLAP * 2,
    )


def _truncate_to_max_tokens(text: str) -> str:
    """Truncate a single string so it never exceeds the embedding model's limit.

    Defends against rare splitter edge cases (e.g. a single "word" longer than
    chunk_size) and also caps long user queries.
    """
    tok = config.get_embed_tokenizer()
    if tok is None:
        return text
    ids = tok.encode(text, add_special_tokens=False)
    budget = config.EMBED_MAX_TOKENS - 16  # margin for special / instruction tokens
    if len(ids) <= budget:
        return text
    return tok.decode(ids[:budget], skip_special_tokens=True)


# Embedding Service Logic
class CustomEmbeddings(Embeddings):
    def embed_query(self, text: str) -> List[float]:
        embed_model = config.get_embed_model()
        m = embed_model.lower()
        if "e5" in m and "instruct" in m:
            text = (
                "Instruct: Given a question, retrieve passages from the "
                "knowledge base that answer it\nQuery: " + text
            )
        # Truncate after prefixing so the combined sequence stays under the cap.
        text = _truncate_to_max_tokens(text)
        payload = {"model": embed_model, "input": [text]}
        try:
            logger.info(f"Sending embedding request to {config.EMBEDDING_URL}")
            resp = requests.post(config.EMBEDDING_URL, json=payload, timeout=config.EMBEDDING_TIMEOUT)
            resp.raise_for_status()
            logger.info("Embedding request successful")
            return resp.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding failed: {e}", exc_info=True)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        texts = [_truncate_to_max_tokens(t) for t in texts]
        payload = {"model": config.get_embed_model(), "input": texts}
        try:
            logger.info(f"Sending batch embedding request for {len(texts)} texts to {config.EMBEDDING_URL}")
            resp = requests.post(config.EMBEDDING_URL, json=payload, timeout=config.EMBEDDING_TIMEOUT)
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in data]
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}", exc_info=True)
            raise


# Knowledge Base Logic
class KnowledgeBase:
    def __init__(self):
        self._client = None
        self.vector_store = None
        self.collection_name = "rag_collection"
        # Serialises build/retrieve/clear so concurrent /process callers
        # cannot observe a partially rebuilt collection. process_rag_logic
        # runs in asyncio.to_thread, so a threading.Lock is the right primitive.
        self._lock = threading.Lock()

    @property
    def client(self):
        if not self._client:
            if config.CHROMADB_URL:
                parsed = urllib.parse.urlparse(config.CHROMADB_URL)
                host = parsed.hostname or "localhost"
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                ssl = parsed.scheme == "https"
                self._client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
            else:
                self._client = chromadb.HttpClient(host=config.CHROMADB_HOST, port=config.CHROMADB_PORT)
        return self._client

    def build(self, file_paths: List[str]):
        """Process files and upload to ChromaDB."""
        with self._lock:
            self.clear_locked()  # Reset before build (lock already held)
            all_docs = []
            for path in file_paths:
                if path.endswith(".pdf"):
                    all_docs.extend(PyMuPDFLoader(path).load())
                elif path.endswith(".txt"):
                    all_docs.extend(TextLoader(path).load())

            splitter = _make_splitter()
            chunks = splitter.split_documents(all_docs)

            if chunks:
                logger.info(f"Embedding {len(chunks)} chunks...")
                self.vector_store = Chroma.from_documents(
                    documents=chunks,
                    embedding=CustomEmbeddings(),
                    client=self.client,
                    collection_name=self.collection_name,
                )
                logger.info("Build complete.")
                return f"Processed {len(chunks)} chunks."
            return "No text found."

    def retrieve(self, query: str, k: int = 0) -> str:
        """Return concatenated chunk text for the top-k results, or "" if no docs are indexed."""
        if k <= 0:
            k = config.TOP_K_DOCS
        safe_query = query.replace("\r", "").replace("\n", "")
        logger.info(f"Retrieving documents for query: {safe_query}")
        with self._lock:
            if not self.vector_store:
                try:
                    self.vector_store = Chroma(
                        client=self.client,
                        collection_name=self.collection_name,
                        embedding_function=CustomEmbeddings(),
                    )
                except Exception:
                    logger.error("Could not reconnect to ChromaDB.", exc_info=True)

            if self.vector_store is None:
                logger.warning("Vector store is None, returning empty result.")
                return ""

            logger.info("Invoking retriever...")
            docs = self.vector_store.as_retriever(search_kwargs={"k": k}).invoke(query)
        logger.info(f"Retrieved {len(docs)} documents.")
        return "\n\n---\n\n".join([d.page_content for d in docs])

    def clear(self):
        with self._lock:
            self.clear_locked()

    def clear_locked(self):
        """Drop the collection. Caller must hold self._lock."""
        try:
            self.client.delete_collection(self.collection_name)
            self.vector_store = None
        except NotFoundError:
            logger.warning(f"Collection '{self.collection_name}' not found for deletion, skipping.")
        except Exception as e:
            logger.error(f"Failed to clear collection '{self.collection_name}': {e}", exc_info=True)
