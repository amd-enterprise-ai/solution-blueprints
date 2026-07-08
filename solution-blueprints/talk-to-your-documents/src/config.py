# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import sys
import time
import urllib.parse
from functools import lru_cache

import requests

# All configuration is read from environment variables set by the Helm template.

TITLE = "Talk to your documents"
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))

EMBEDDING_URL = os.getenv("EMBEDDING_URL", "")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")
VLLM_MODEL = os.getenv("VLLM_MODEL", "")  # Optional override; bypasses /models auto-detection.
CHROMADB_URL = os.getenv("CHROMADB_URL", "")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_TIMEOUT: int = int(os.getenv("EMBEDDING_TIMEOUT", "120"))

# RAG Params
# CHUNK_SIZE/CHUNK_OVERLAP are interpreted as TOKENS when the embedding-model
# tokenizer is available (default), otherwise as a conservative char-count.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "300"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "60"))
TOP_K_DOCS = int(os.getenv("TOP_K_DOCS", "6"))

# Hard upper bound enforced by the embedding model (e.g. 512 for e5-large).
# Inputs are truncated below this to leave margin for special / instruction tokens.
EMBED_MAX_TOKENS = int(os.getenv("EMBED_MAX_TOKENS", "512"))

# Number of retries when auto-detecting model names at first use.
# The init container already gates the pod on /health, so this is a safety
# net for transient blips rather than a long startup wait.
INIT_RETRIES = int(os.getenv("INIT_RETRIES", "3"))


def _detect_model(base_url: str, with_auth: bool = False) -> str:
    """Query an OpenAI-compatible /models endpoint and return the first model id.

    Raises RuntimeError after INIT_RETRIES failed attempts. The Helm init
    container guarantees the service is reachable before the app starts, so
    failures here indicate a real misconfiguration rather than a startup race.
    """
    base = base_url if base_url.endswith("/") else f"{base_url}/"
    url = urllib.parse.urljoin(base, "models")
    headers = {"Authorization": f"Bearer {VLLM_API_KEY}"} if with_auth and VLLM_API_KEY else {}
    last_err = ""
    for retry in range(INIT_RETRIES):
        if retry != 0:
            time.sleep(2**retry)
        try:
            r = requests.get(url, headers=headers, timeout=5.0)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return data[0]["id"]
                last_err = f"{url} returned no models"
            else:
                last_err = f"{url} returned HTTP {r.status_code}"
        except Exception as e:
            last_err = f"{url}: {e}"
            print(f"Model auto-detection failed for {base_url}: {e}", file=sys.stderr)
    raise RuntimeError(f"Failed to auto-detect model after {INIT_RETRIES} attempts: {last_err}")


@lru_cache(maxsize=1)
def get_vllm_base_url() -> str:
    url = os.getenv("VLLM_URL", "")
    if not url:
        raise RuntimeError("VLLM_URL env var must be set")
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


@lru_cache(maxsize=1)
def get_embed_model() -> str:
    """Return the embedding model name auto-detected from EMBEDDING_URL."""
    env_model = os.getenv("EMBED_MODEL_NAME")
    if env_model:
        return env_model
    if not EMBEDDING_URL:
        raise RuntimeError("EMBEDDING_URL env var must be set")
    base = EMBEDDING_URL.rstrip("/")
    if base.endswith("/embeddings"):
        base = base[: -len("/embeddings")]
    return _detect_model(base)


@lru_cache(maxsize=1)
def get_gen_model() -> str:
    """Return the generation model name; respects VLLM_MODEL override."""
    if VLLM_MODEL:
        return VLLM_MODEL
    return _detect_model(get_vllm_base_url(), with_auth=True)


# Lazy tokenizer loader for token-aware chunking + input truncation.
_TOKENIZER_CACHE: dict = {}


def get_embed_tokenizer():
    """Return a HuggingFace tokenizer for the embedding model, or None if unavailable.

    Loaded once and cached. A None result is also cached so we don't retry
    repeatedly when transformers/sentencepiece aren't installed or the model
    can't be downloaded.
    """
    if "tokenizer" in _TOKENIZER_CACHE:
        return _TOKENIZER_CACHE["tokenizer"]
    model = get_embed_model()
    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(model)
    except Exception as e:
        print(
            f"Could not load tokenizer for {model}: {e}. "
            "Falling back to char-based chunking (less accurate for non-English text).",
            file=sys.stderr,
        )
        tok = None
    _TOKENIZER_CACHE["tokenizer"] = tok
    return tok
