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


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[: -len("/v1")]
    if not normalized.startswith("http://") and not normalized.startswith("https://"):
        normalized = "http://" + normalized
    return normalized


def _auth_header_from_api_key(api_key: str | None) -> str | None:
    if api_key:
        normalized = api_key.strip()
        if not normalized:
            return None
        if normalized.lower().startswith("bearer "):
            token = normalized[7:].strip()
            return f"Bearer {token}" if token else None
        return f"Bearer {normalized}"
    return None


async def fetch_model_name(base_url: str, auth_header: str | None = None) -> str:
    base_url = _normalize_openai_base_url(base_url)
    models_url = f"{base_url}/v1/models"

    async with _MODEL_LOCK:
        if base_url in _MODEL_CACHE:
            return _MODEL_CACHE[base_url]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(models_url, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch models from {models_url}: {resp.status_code} {resp.text}")

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


async def proxy_chat_completion(req, config: dict, incoming_auth: str | None = None):
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
            logger.exception("Classifier failed for policy '%s'", llm_router.policy)
            if "Unknown" in classes:
                logger.warning(
                    "Falling back to 'Unknown' route because classifier failed for policy '%s': %s",
                    llm_router.policy,
                    e,
                )
                llm_name = "Unknown"
            else:
                return error_response("routing_error_classifier", f"Classifier request failed: {e}", 503, "router")
    llm = next((llm_def for llm_def in policy["models"] if llm_def["name"] == llm_name), None)
    if not llm:
        return error_response(
            "routing_error_model_not_found",
            f"LLM '{llm_name}' not found in policy '{policy['rule_name']}'",
            400,
            "router",
        )

    base_url = _normalize_openai_base_url(llm["base_url_path"])
    api_key = llm.get("api_key")
    logger.debug("LLM config for '%s': api_key_present=%s", llm_name, "yes" if api_key else "no")

    # Check if api_key is still a placeholder
    if api_key and api_key.startswith("${"):
        logger.warning("API key is still a placeholder (not expanded by config loader)")

    primary_auth = _auth_header_from_api_key(api_key) or incoming_auth
    logger.info(
        "Using auth: source=%s (api_key=%s, incoming=%s)",
        "api_key" if _auth_header_from_api_key(api_key) else "incoming",
        "yes" if api_key else "no",
        "yes" if incoming_auth else "no",
    )
    fallback_auth = incoming_auth if _auth_header_from_api_key(api_key) and incoming_auth else None

    model_name = (llm.get("model_name") or "").strip() or (req.model or "").strip()
    if not model_name:
        try:
            model_name = await fetch_model_name(base_url, primary_auth)
        except Exception as first_error:
            if fallback_auth:
                try:
                    model_name = await fetch_model_name(base_url, fallback_auth)
                    primary_auth = fallback_auth
                except Exception:
                    logger.exception("Failed to discover model for backend '%s'", llm_name)
                    return error_response(
                        "routing_error_model_discovery",
                        (
                            f"Model discovery failed for '{llm_name}': {first_error}. "
                            "Set model_name in routing config or include model in request to avoid /v1/models discovery."
                        ),
                        502,
                        "router",
                    )
            else:
                logger.exception("Failed to discover model for backend '%s'", llm_name)
                return error_response(
                    "routing_error_model_discovery",
                    (
                        f"Model discovery failed for '{llm_name}': {first_error}. "
                        "Set model_name in routing config or include model in request to avoid /v1/models discovery."
                    ),
                    502,
                    "router",
                )

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
    if primary_auth:
        headers["Authorization"] = primary_auth
    if req.stream:
        return await stream_llm(api_url, body, headers, 200, llm_name)
    else:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                resp = await client.post(api_url, json=body, headers=headers)
                if resp.status_code in (401, 403) and fallback_auth and headers.get("Authorization") != fallback_auth:
                    retry_headers = dict(headers)
                    retry_headers["Authorization"] = fallback_auth
                    resp = await client.post(api_url, json=body, headers=retry_headers)
                exclude = {"content-length", "transfer-encoding", "content-encoding", "connection"}
                response_headers = {"X-Chosen-Classifier": llm_name}
                for k, v in resp.headers.items():
                    if k.lower() not in exclude:
                        response_headers[k] = v
                data = await resp.aread()
                return Response(
                    content=data, status_code=resp.status_code, headers=response_headers, media_type="application/json"
                )
        except httpx.RequestError as e:
            logger.exception("Backend request failed for model '%s'", llm_name)
            return error_response(
                "routing_error_backend_unreachable",
                f"Backend request failed for '{llm_name}' at {api_url}: {e}",
                502,
                "router",
            )


def build_classifier_messages(messages):
    if CONTEXT_MODE == "full":
        relevant = messages[-CONTEXT_TURNS * 2 :]
    else:  # user_only
        relevant = [m for m in messages if m.role == "user"][-CONTEXT_TURNS:]

    return [{"role": m.role, "content": m.content} for m in relevant]
