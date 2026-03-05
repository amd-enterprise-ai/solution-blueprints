# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from fastapi import FastAPI

from .modelClient import ClassificationLLMClient
from .schemas import ClassifierRequest, ClassifierResponse

app = FastAPI(title="Routing Classifier Service", description="API for prompt classification", version="1.0.0")

client = ClassificationLLMClient()


@app.post("/classify", response_model=ClassifierResponse)
async def classify(request: ClassifierRequest):
    print(f"[DEBUG] Received classification request: messages='{request.messages}', classes={request.classes}")

    result = await client.classify(request.messages, request.classes or [])
    chosen_class = result.get("class")

    if chosen_class is None:
        print("[WARN] Model failed to return a valid class")
        chosen_class = "Unknown"

    return ClassifierResponse(chosen_class=chosen_class)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("classifierApp.main:app", host="0.0.0.0", port=8010, reload=False)
