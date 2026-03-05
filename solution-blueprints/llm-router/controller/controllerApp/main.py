# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .config import mask_config
from .proxy import proxy_chat_completion
from .schemas import ChatCompletionRequest

load_dotenv()

app = FastAPI()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
_config = None

CONFIG_PATH = os.getenv("ROUTER_CONTROLLER_CONFIG", "/config/config.yaml")


def load_config(path: str):
    logger.debug("Reading config file: %s", path)
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_config():
    global _config
    if _config is None:
        _config = load_config(CONFIG_PATH)
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
        return await proxy_chat_completion(req, config)
    except Exception as e:
        logging.exception("Exception in /v1/chat/completions endpoint")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "type": "client_error",
                    "message": "An internal error has occurred.",
                    "status": 400,
                    "source": "client",
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
