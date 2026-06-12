# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os
import re

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bff-proxy")

app = FastAPI()

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
REACT_URL = os.getenv("REACT_BASE_URL", "http://localhost:80")

client = httpx.AsyncClient(
    timeout=httpx.Timeout(1200.0),
    follow_redirects=True,
)

logger.info(f"Backend URL: {BACKEND_URL}")
logger.info(f"React URL: {REACT_URL}")


def sanitize_log_input(value: str) -> str:
    """Remove characters that could be used for log injection"""
    if not value:
        return ""
    return value.replace("\r", "").replace("\n", "")


def validate_path(path: str) -> str:
    """Validate path to prevent SSRF attacks"""
    # Remove any path traversal attempts
    cleaned = path.replace("../", "").replace("..\\", "")

    # Allow only safe characters (alphanumeric, slashes, dots, hyphens, underscores)
    if not re.match(r"^[a-zA-Z0-9\/\.\-_]*$", cleaned):
        raise ValueError("Invalid path characters")

    return cleaned


@app.get("/health")
async def health():
    return {"status": "healthy", "backend": BACKEND_URL, "react": REACT_URL}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    # Validate path to prevent SSRF
    try:
        validated_path = validate_path(path)
    except ValueError as e:
        logger.warning(f"Invalid path attempted: {sanitize_log_input(path)}")
        return StreamingResponse(content="Invalid path", status_code=400)

    # Sanitize path for logging
    safe_path = sanitize_log_input(path)

    if path.startswith("api/"):
        backend_path = validated_path.replace("api/", "", 1)
        target_url = f"{BACKEND_URL}/{backend_path}".rstrip("/")
        logger.info(f"Proxying API {request.method} /{safe_path}")
    else:
        target_url = f"{REACT_URL}/{validated_path}".rstrip("/") if validated_path else REACT_URL
        logger.info(f"Proxying static {request.method} /{safe_path}")

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    resp = await client.request(
        method=request.method,
        url=target_url,
        headers=headers,
        content=body,
        params=request.query_params,
    )

    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )
