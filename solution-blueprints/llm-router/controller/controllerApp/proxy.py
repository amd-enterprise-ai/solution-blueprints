# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import logging
import os

import httpx
from fastapi.responses import Response, StreamingResponse

from .error import error_response
from .routerClassifier import classify

logger = logging.getLogger(__name__)

CONTEXT_MODE = os.getenv("CLASSIFIER_CONTEXT_MODE", "user_only").lower()
CONTEXT_TURNS = int(os.getenv("CLASSIFIER_CONTEXT_TURNS", "5"))

_MODEL_CACHE: dict[str, str] = {}
_MODEL_LOCK = asyncio.Lock()


async def fetch_model_name(base_url: str, api_key: str | None = None) -> str:
    base_url = base_url.rstrip("/")

    async with _MODEL_LOCK:
        if base_url in _MODEL_CACHE:
            return _MODEL_CACHE[base_url]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/v1/models", headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch models from {base_url}: {resp.status_code} {resp.text}")

        data = resp.json()
        if not data.get("data"):
            raise RuntimeError(f"No models returned from {base_url}")

        model_name = data["data"][0]["id"]
        _MODEL_CACHE[base_url] = model_name
        return model_name


async def stream_llm(api_url, body, headers, status, classifier_name):
    exclude = {"content-length", "transfer-encoding", "content-encoding", "connection"}
    response_headers = {"X-Chosen-Classifier": classifier_name}

    async def bytegen():
        client = httpx.AsyncClient(timeout=None)
        resp = None
        try:
            async with client.stream("POST", api_url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    content = await resp.aread()
                    raise RuntimeError(("__LLM_NON_OK__", resp.status_code, content, dict(resp.headers)))

                for k, v in resp.headers.items():
                    if k.lower() not in exclude:
                        response_headers[k] = v

                try:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk
                        await asyncio.sleep(0)
                except (httpx.RemoteProtocolError, httpx.StreamError, httpx.ReadTimeout) as e:
                    logger.warning("LLM stream error while iterating: %s", e)
                    return
                except Exception as e:
                    logger.exception("Unexpected error while streaming from LLM: %s", e)
                    return
        finally:
            if resp is not None:
                try:
                    await resp.aclose()
                except Exception as e:
                    logger.warning("Failed to close response: %s", e)
            try:
                await client.aclose()
            except Exception as e:
                logger.warning("Failed to close client: %s", e)

    return StreamingResponse(bytegen(), status_code=status, headers=response_headers, media_type="text/event-stream")


async def proxy_chat_completion(req, config: dict):
    llm_router = req.llm_router
    policy = next((p for p in config["routing_rules"] if p["rule_name"] == llm_router.policy), None)
    if not policy:
        return error_response(
            "routing_error_policy_not_found", f"Policy '{llm_router.policy}' not found", 400, "router"
        )

    if llm_router.routing_strategy == "manual":
        llm_name = llm_router.model
    else:
        classifier_messages = build_classifier_messages(req.messages)
        classes = [llm_def["name"] for llm_def in policy["models"]]
        try:
            llm_name = await classify(classifier_messages, classes, policy["classifier_endpoint"])
        except Exception as e:
            return error_response("routing_error_classifier", "Internal classifier error occurred.", 503, "router")
    llm = next((llm_def for llm_def in policy["models"] if llm_def["name"] == llm_name), None)
    if not llm:
        return error_response(
            "routing_error_model_not_found",
            f"LLM '{llm_name}' not found in policy '{policy['rule_name']}'",
            400,
            "router",
        )

    base_url = llm["base_url_path"].rstrip("/")
    api_key = llm.get("api_key")
    model_name = llm.get("model_name") or await fetch_model_name(base_url, api_key)
    api_url = f"{base_url}/v1/chat/completions"

    body = {
        "model": model_name,
        "messages": [m.dict() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "n": req.n,
        "stream": req.stream,
        "stop": req.stop,
    }
    body = {k: v for k, v in body.items() if v is not None}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if req.stream:
        return await stream_llm(api_url, body, headers, 200, llm_name)
    else:
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(api_url, json=body, headers=headers)
            exclude = {"content-length", "transfer-encoding", "content-encoding", "connection"}
            response_headers = {"X-Chosen-Classifier": llm_name}
            for k, v in resp.headers.items():
                if k.lower() not in exclude:
                    response_headers[k] = v
            data = await resp.aread()
            return Response(
                content=data, status_code=resp.status_code, headers=response_headers, media_type="application/json"
            )


def build_classifier_messages(messages):
    if CONTEXT_MODE == "full":
        relevant = messages[-CONTEXT_TURNS * 2 :]
    else:  # user_only
        relevant = [m for m in messages if m.role == "user"][-CONTEXT_TURNS:]

    return [{"role": m.role, "content": m.content} for m in relevant]
