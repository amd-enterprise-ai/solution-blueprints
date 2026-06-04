# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import load_config, mask_config
from .proxy import proxy_chat_completion
from .schemas import ChatCompletionRequest

load_dotenv()

app = FastAPI()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
_config = None

CONFIG_PATH = os.getenv("ROUTER_CONTROLLER_CONFIG", "/config/config.yaml")


def get_config():
    global _config
    if _config is None:
        logger.debug("Reading config file: %s", CONFIG_PATH)
        _config = load_config(CONFIG_PATH)
        logger.info("Config loaded successfully")
        if _config.get("routing_rules"):
            logger.info("Loaded %d routing rules", len(_config.get("routing_rules", [])))
            for rule in _config.get("routing_rules", []):
                logger.info("  Rule: %s with %d models", rule.get("rule_name"), len(rule.get("models", [])))
                for model in rule.get("models", [])[:1]:  # Log just the first model of each rule
                    logger.info("    First model: %s", model.get("name"))
    return _config


@app.get("/health")
async def health():
    return {"status": "OK"}


@app.get("/config")
async def config():
    config = get_config()
    return mask_config(config)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
        req = ChatCompletionRequest(**data)
        config = get_config()
        return await proxy_chat_completion(req, config, request.headers.get("authorization"))
    except ValidationError as e:
        logger.warning("Invalid chat completion request payload: %s", e)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "type": "client_error_validation",
                    "message": "Request payload validation failed.",
                    "status": 422,
                    "source": "client",
                    "details": e.errors(),
                }
            },
        )
    except Exception as e:
        logger.exception("Unhandled exception in /v1/chat/completions endpoint")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "type": "router_error_internal",
                    "message": f"Unhandled controller error: {e}",
                    "status": 500,
                    "source": "router",
                }
            },
        )


@app.post("/completions")
async def completions(request: Request):
    return await chat_completions(request)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8084))
    uvicorn.run("controllerApp.main:app", host="0.0.0.0", port=port, reload=False)
