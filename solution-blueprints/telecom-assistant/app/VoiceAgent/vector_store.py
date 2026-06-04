# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
import asyncio
import logging
import re
import urllib

import chromadb
from chromadb.config import Settings
from openai import AsyncOpenAI
from rank_bm25 import BM25Okapi
from settings import settings

logger = logging.getLogger(__name__)


class AIMEmbeddings:

    def __init__(self, base_url: str, api_key: str):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        res = await self.client.embeddings.create(
            model=settings.embeddings_model,
            input=texts,
        )
        return [item.embedding for item in res.data]


class ChromaHybridStore:
    def __init__(self):
        chroma_url = settings.chroma_url
        if chroma_url:
            parsed = urllib.parse.urlparse(chroma_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            ssl = parsed.scheme == "https"
            logger.info(
                f"ChromaDB Client Version: {chromadb.__version__}, {host}, {port} ({"Secured" if ssl else "Unsecured"})"
            )
            self.client = chromadb.HttpClient(
                host=host, port=port, ssl=ssl, settings=Settings(anonymized_telemetry=False)
            )
        else:
            raise ValueError("CHROMA_URL is not configured")

        self.embedder = AIMEmbeddings(base_url=settings.embeddings_url, api_key=settings.embeddings_api_key)

        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def normalize_text(text: str) -> list[str]:
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        tokens = text.split()
        return tokens

    async def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict],
        ids: list[str],
        clear: bool = False,
    ) -> None:
        if not texts:
            return

        if clear:

            def _clear():
                existing = self.collection.get()
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])

            await asyncio.to_thread(_clear)

        embeddings = await self.embedder.embed(texts)

        def _add():
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings,
            )

        await asyncio.to_thread(_add)

    def _keyword_candidate_search(
        self,
        query: str,
        k: int = 50,
    ) -> list[str]:

        query_tokens = self.normalize_text(query)
        if not query_tokens:
            return []

        where_clauses = [{"$contains": token} for token in query_tokens]

        results = self.collection.get(
            where_document={"$or": where_clauses},
            limit=k,
            include=["documents"],
        )

        if not results or not results.get("ids"):
            return []

        documents = results["documents"]
        ids = results["ids"]

        tokenized_corpus = [self.normalize_text(doc) for doc in documents]

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)

        ranked = sorted(
            zip(ids, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return [doc_id for doc_id, _ in ranked]

    async def hybrid_search(
        self,
        query: str,
        k: int = 4,
        candidate_multiplier: int = 5,
        rrf_k: int = 10,
        dense_weight: float = 2.0,
        keyword_weight: float = 1.0,
    ) -> list[dict]:
        if not query.strip():
            return []

        q_emb = (await self.embedder.embed([query]))[0]

        dense_limit = k * candidate_multiplier

        sem_res = self.collection.query(
            query_embeddings=[q_emb],
            n_results=dense_limit,
            include=["documents", "metadatas"],
        )

        sem_ids = []
        if sem_res and sem_res.get("ids") and sem_res["ids"][0]:
            sem_ids = sem_res["ids"][0]

        kw_ids = await asyncio.to_thread(
            self._keyword_candidate_search,
            query,
            k=dense_limit,
        )

        rrf_scores: dict = {}

        for rank, doc_id in enumerate(sem_ids, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + dense_weight / (rrf_k + rank)

        for rank, doc_id in enumerate(kw_ids, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + keyword_weight / (rrf_k + rank)

        if not rrf_scores:
            return []

        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda x: rrf_scores[x],
            reverse=True,
        )[:k]

        final_docs = self.collection.get(
            ids=sorted_ids,
            include=["documents", "metadatas"],
        )

        id_to_data = {
            id_: {
                "document": doc,
                "metadata": meta,
            }
            for id_, doc, meta in zip(
                final_docs["ids"],
                final_docs["documents"],
                final_docs["metadatas"],
            )
        }

        output = []
        for doc_id in sorted_ids:
            if doc_id in id_to_data:
                output.append(
                    {
                        "id": doc_id,
                        "document": id_to_data[doc_id]["document"],
                        "metadata": id_to_data[doc_id]["metadata"],
                        "rrf_score": rrf_scores[doc_id],
                    }
                )

        return output
