# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import sys
import time
import urllib.parse

import requests

# App Settings
TITLE = "Talk to your documents"
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))

# Services
INFINITY_EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding-e5-large:7997/embeddings")
VLLM_BASE_URL = os.getenv("VLLM_URL", "http://llama-3-3-70b:8000/v1")
CHROMADB_URL = os.getenv("CHROMADB_URL", "")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb-store")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))

# Models
INIT_RETRIES = 5


def init_embed_model():
    for retry in range(INIT_RETRIES):
        if retry != 0:
            print(
                f"Couldn't retrieve embedding model name - Infinity probably not up yet. Waiting {2**retry} seconds...",
                file=sys.stderr,
            )
            time.sleep(2**retry)
        print(f"Trying to retrieve embedding model name (attempt {retry+1})", file=sys.stderr)
        try:
            url = urllib.parse.urljoin(INFINITY_EMBEDDING_URL, "models")
            r = requests.get(url, timeout=2.0)
            if r.status_code == 200:
                try:
                    return r.json()["data"][0]["id"]
                except (KeyError, IndexError):
                    pass
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error when retrieving embedding model name: {e}", file=sys.stderr)
    raise RuntimeError("Failed to retrieve embedding model name")


EMBED_MODEL = init_embed_model()


def init_gen_model():
    for retry in range(INIT_RETRIES):
        if retry != 0:
            print(
                f"Couldn't retrieve model name - AIM probably not up yet. Waiting {2**retry} seconds...",
                file=sys.stderr,
            )
            time.sleep(2**retry)
        print(f"Trying to retrieve model name (attempt {retry+1})", file=sys.stderr)
        try:
            # Ensure URL ends with / before joining if it doesn't, to keep the path
            base = VLLM_BASE_URL
            if not base.endswith("/"):
                base += "/"
            url = urllib.parse.urljoin(base, "models")

            r = requests.get(url, timeout=2.0)
            if r.status_code == 200:
                try:
                    return r.json()["data"][0]["id"]
                except (KeyError, IndexError):
                    pass
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error when retrieving embedding model name: {e}", file=sys.stderr)
    raise RuntimeError("Failed to retrieve model name")


GEN_MODEL = init_gen_model()

# RAG Params
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
