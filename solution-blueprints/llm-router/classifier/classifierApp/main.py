# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import logging
import os
from typing import Any, Dict, List, Protocol

from fastapi import FastAPI

from .schemas import ClassifierRequest, ClassifierResponse, Message


class ClassifierClientProtocol(Protocol):
    async def classify(self, messages: List[Message], classes: List[str] | None) -> Dict[str, Any]:
        pass


CLASSIFIER_APPROACH = os.getenv("CLASSIFIER_APPROACH", "embedding")
CLASSIFIER_REQUEST_TIMEOUT_SECONDS = float(os.getenv("CLASSIFIER_REQUEST_TIMEOUT_SECONDS", "20"))

logger = logging.getLogger(__name__)

app = FastAPI(title="Routing Classifier Service", version="1.0.0")

client: ClassifierClientProtocol

if CLASSIFIER_APPROACH == "llm":
    from .llmClient import ClassificationLLMClient

    client = ClassificationLLMClient()
elif CLASSIFIER_APPROACH == "embedding":
    from .embeddingClient import EmbeddingClassifierClient

    client = EmbeddingClassifierClient()
else:
    raise RuntimeError(f"Unknown CLASSIFIER_APPROACH: '{CLASSIFIER_APPROACH}'. Use 'embedding' or 'llm'.")


@app.post("/classify", response_model=ClassifierResponse)
async def classify(request: ClassifierRequest):
    try:
        result = await asyncio.wait_for(
            client.classify(request.messages, request.classes),
            timeout=CLASSIFIER_REQUEST_TIMEOUT_SECONDS,
        )
        chosen_class = result.get("class") or "Unknown"
        return ClassifierResponse(chosen_class=chosen_class)
    except Exception as e:
        logger.exception("Classifier request failed, returning Unknown fallback: %s", e)
        return ClassifierResponse(chosen_class="Unknown")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("classifierApp.main:app", host="0.0.0.0", port=8010, reload=False)
