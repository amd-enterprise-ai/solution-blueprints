# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
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


# Embedding Service Logic
class CustomEmbeddings(Embeddings):
    def embed_query(self, text: str) -> List[float]:
        payload = {"model": config.EMBED_MODEL, "input": [text]}
        try:
            logger.info(f"Sending embedding request to {config.INFINITY_EMBEDDING_URL}")
            resp = requests.post(config.INFINITY_EMBEDDING_URL, json=payload, timeout=30)
            resp.raise_for_status()
            logger.info("Embedding request successful")
            return resp.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding failed: {e}", exc_info=True)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(t) for t in texts]


# Knowledge Base Logic
class KnowledgeBase:
    def __init__(self):
        self._client = None
        self.vector_store = None
        self.collection_name = "rag_collection"

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
        """Process files and upload to ChromaDB"""
        self.clear()  # Reset before build
        all_docs = []
        for path in file_paths:
            if path.endswith(".pdf"):
                all_docs.extend(PyMuPDFLoader(path).load())
            elif path.endswith(".txt"):
                all_docs.extend(TextLoader(path).load())

        splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
        chunks = splitter.split_documents(all_docs)

        if chunks:
            logger.info(f"Embedding {len(chunks)} chunks...")
            self.vector_store = Chroma.from_documents(
                documents=chunks, embedding=CustomEmbeddings(), client=self.client, collection_name=self.collection_name
            )
            logger.info("Build complete.")
            return f"Processed {len(chunks)} chunks."
        return "No text found."

    def retrieve(self, query: str, k: int = 5) -> str:
        """Returns formatted string of context"""
        safe_query = query.replace("\r", "").replace("\n", "")
        logger.info(f"Retrieving documents for query: {safe_query}")
        if not self.vector_store:
            try:
                self.vector_store = Chroma(
                    client=self.client, collection_name=self.collection_name, embedding_function=CustomEmbeddings()
                )
            except Exception:
                logger.error("Could not reconnect to ChromaDB.", exc_info=True)

        if self.vector_store is None:
            logger.warning("Vector store is None, returning empty result.")
            return "No documents uploaded. Please upload a document first."

        logger.info("Invoking retriever...")
        docs = self.vector_store.as_retriever(search_kwargs={"k": k}).invoke(query)
        logger.info(f"Retrieved {len(docs)} documents.")
        return "\n\n---\n\n".join([d.page_content for d in docs])

    def clear(self):
        try:
            self.client.delete_collection(self.collection_name)
            self.vector_store = None
        except NotFoundError:
            logger.warning(f"Collection '{self.collection_name}' not found for deletion, skipping.")
        except Exception as e:
            logger.error(f"Failed to clear collection '{self.collection_name}': {e}", exc_info=True)
