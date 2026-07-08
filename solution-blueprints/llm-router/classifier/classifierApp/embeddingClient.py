# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import logging
import os
from typing import Any, Dict, List

import httpx
import numpy as np

from .schemas import Message

logger = logging.getLogger(__name__)
log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()

logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _sanitize_for_logging(value: Any) -> str:
    """
    Return a log-safe string representation of the given value by removing
    newline and carriage-return characters that could be used for log injection.
    """

    def _clean_str(s: str) -> str:
        return s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    if isinstance(value, (list, tuple)):
        cleaned_items = []
        for item in value:
            if isinstance(item, str):
                cleaned_items.append(_clean_str(item))
            else:
                cleaned_items.append(_clean_str(str(item)))
        return "[" + ", ".join(cleaned_items) + "]"

    if isinstance(value, str):
        return _clean_str(value)

    return _clean_str(str(value))


def _sanitize_for_log(value: Any) -> str:
    """
    Convert arbitrary value to a log-safe string by removing control characters
    that could break log formatting.
    """
    text = str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return "".join(ch for ch in text if ch >= " " or ch == "\t")


MODEL_NAME = os.getenv("CLASSIFIER_EMBEDDING_MODEL_NAME", "").strip("\"'").strip()

class_embeddings: np.ndarray | None = None
class_names: List[str] = []
class_descriptions: List[str] = []

_init_lock = asyncio.Lock()


async def fetch_classes_config(controller_url: str) -> Dict[str, str]:
    """Load class names and descriptions from controller service"""
    url = f"{controller_url.rstrip('/')}/config"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            classes_dict: Dict[str, str] = {}
            for rule in data.get("routing_rules", []):
                for model in rule.get("models", []):
                    name = model.get("name")
                    desc = model.get("description", "").strip()
                    if name and desc:
                        if name in classes_dict and classes_dict[name] != desc:
                            logger.debug("Duplicate class %r with different descriptions", name)
                        classes_dict[name] = desc
            if not classes_dict:
                raise ValueError("No classes with descriptions found in config")
            return classes_dict
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {url}: {e}")


async def get_embeddings(embedding_url: str, texts: List[str]) -> np.ndarray:
    """Fetch embeddings from the OpenAI-compatible embedding server"""
    payload = {
        "model": MODEL_NAME,
        "input": texts,
        "encoding_format": "float",
        "truncate_prompt_tokens": 512,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(embedding_url, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()["data"]
        embs = [item["embedding"] for item in data]
        return np.array(embs)


def normalize_embeddings(embs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    return embs / norms.clip(min=1e-12)


async def load_class_embeddings(embedding_url: str, controller_url: str):
    """Load config and compute embeddings for class descriptions (called once)"""
    global class_embeddings, class_names, class_descriptions

    config = await fetch_classes_config(controller_url)
    class_descriptions = list(config.values())
    class_names = list(config.keys())

    if not class_descriptions:
        raise RuntimeError("No class descriptions loaded")

    raw_embs = await get_embeddings(embedding_url, class_descriptions)
    class_embeddings = normalize_embeddings(raw_embs)

    logger.info("Loaded classes:")
    for name, desc in zip(class_names, class_descriptions):
        logger.info("  - %s: %s...", name, desc[:120])
    logger.info("Embeddings shape: %s", class_embeddings.shape if class_embeddings is not None else "None")


class EmbeddingClassifierClient:
    def __init__(self):
        embedding_url_env = os.getenv("EMBEDDING_URL")
        if embedding_url_env is None:
            raise RuntimeError("EMBEDDING_URL environment variable is required")
        self.embedding_url = embedding_url_env

        controller_url = os.getenv("CONTROLLER_URL")
        if controller_url is None:
            raise RuntimeError("CONTROLLER_URL environment variable is required")
        self.controller_url = controller_url

        self.initialized = False

    async def initialize(self):
        if self.initialized:
            return

        async with _init_lock:
            if not self.initialized:
                await load_class_embeddings(self.embedding_url, self.controller_url)
                self.initialized = True

    async def classify(
        self,
        messages: List[Message],
        classes: List[str] | None = None,
    ) -> Dict[str, Any]:
        if not self.initialized:
            await self.initialize()

        if class_embeddings is None or not class_names:
            return {"class": "Unknown"}

        dialogue = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        logger.debug("Dialogue (first 200 chars): %s...", dialogue[:200])

        instruct_text = (
            "Instruct: Given the user message, select the most appropriate category from the available options.\n"
            f"Query: {dialogue}"
        )
        logger.debug("Instruct text: %s", instruct_text)

        query_emb_raw = await get_embeddings(self.embedding_url, [instruct_text])
        query_emb = normalize_embeddings(query_emb_raw)[0]

        if classes:
            filtered_indices = []
            filtered_names = []
            filtered_embs_list = []
            for cls in classes:
                if cls in class_names:
                    idx = class_names.index(cls)
                    filtered_indices.append(idx)
                    filtered_names.append(cls)
                    filtered_embs_list.append(class_embeddings[idx])
            if not filtered_embs_list:
                safe_classes = _sanitize_for_logging(classes)
                logger.warning("No matching classes found for %s", safe_classes)
                return {"class": "Unknown"}
            filtered_embs = np.array(filtered_embs_list)
            active_classes = filtered_names
        else:
            filtered_embs = class_embeddings
            active_classes = class_names

        similarities = np.dot(filtered_embs, query_emb)
        sim_dict = {name: f"{sim:.4f}" for name, sim in zip(active_classes, similarities)}
        sanitized_sim_dict = {_sanitize_for_log(name): _sanitize_for_log(score) for name, score in sim_dict.items()}
        logger.debug("Similarities: %s", sanitized_sim_dict)
        max_idx = int(np.argmax(similarities))
        max_sim = float(similarities[max_idx])

        THRESHOLD = 0.70 if len(active_classes) <= 5 else 0.68

        if max_sim < THRESHOLD:
            chosen = "Unknown"
            logger.debug(
                "Low confidence (%.4f) < %.2f for %d active classes -> Unknown",
                max_sim,
                THRESHOLD,
                len(active_classes),
            )
        else:
            chosen = active_classes[max_idx]
            logger.debug(
                "Selected class with similarity=%.4f from %d active classes",
                max_sim,
                len(active_classes),
            )

        return {"class": chosen}
