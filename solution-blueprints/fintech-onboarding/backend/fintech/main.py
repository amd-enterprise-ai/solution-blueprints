# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Dict, List

import cv2
import numpy as np
from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fintech.barcode import user_data_back_side
from fintech.embedding import compare_faces, extract_embedding
from fintech.liveness import get_liveness_embeddings
from fintech.ocr import user_data_front_side

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/extract_embedding")
async def extract_embedding_endpoint(file: UploadFile = File(...)):
    """Extract face embedding from uploaded photo."""
    data = await file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    if img is None:
        return {"success": False, "reason": "invalid_image"}

    return extract_embedding(img)


@app.post("/compare_faces")
async def compare_faces_endpoint(live_embedding: list[float] = Body(...), doc_embedding: list[float] = Body(...)):
    """Compare two face embeddings."""
    return compare_faces(live_embedding, doc_embedding)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/extract_live_embedding")
async def extract_live_embedding(files: List[UploadFile] = File(...)):
    return await get_liveness_embeddings(files)


@app.post("/extract_user_data")
async def extract_user_data(file: UploadFile = File(...)) -> Dict:
    return await user_data_front_side(file)


@app.post("/extract_barcode_data")
async def extract_barcode_data(file: UploadFile = File(...)) -> Dict:
    return await user_data_back_side(file)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fintech.main:app", host="0.0.0.0", port=8000)
