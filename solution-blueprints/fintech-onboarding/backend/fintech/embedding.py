# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Any, Dict

import numpy as np
from fintech.model import face_app


def extract_embedding(image_bgr: np.ndarray) -> Dict[str, Any]:
    faces = face_app.get(image_bgr)

    if not faces:
        return {"success": False, "reason": "no_face_detected"}

    if len(faces) > 1:
        return {"success": False, "reason": "multiple_faces_detected"}

    face = faces[0]

    embedding = face.embedding
    embedding_norm = embedding / np.linalg.norm(embedding)

    return {
        "success": True,
        "embedding": embedding_norm.tolist(),
        "bbox": face.bbox.tolist(),
        "det_score": float(face.det_score),
        "age": None,
        "gender": None,
        "gender_str": None,
    }


def extract_embedding_largest_face(image_bgr: np.ndarray) -> Dict[str, Any]:
    faces = face_app.get(image_bgr)

    if not faces:
        return {"success": False, "reason": "no_face_detected"}

    def bbox_area(face):
        x1, y1, x2, y2 = face.bbox
        return (x2 - x1) * (y2 - y1)

    face = max(faces, key=bbox_area)

    embedding = face.embedding
    embedding_norm = embedding / np.linalg.norm(embedding)

    return {
        "success": True,
        "embedding": embedding_norm.tolist(),
        "bbox": face.bbox.tolist(),
        "det_score": float(face.det_score),
        "age": None,
        "gender": None,
        "gender_str": None,
        "faces_detected": len(faces),
    }


def compare_faces(live_embedding: list[float], doc_embedding: list[float]) -> Dict[str, Any]:
    if len(live_embedding) != 128 or len(doc_embedding) != 128:
        return {"match": False, "reason": "invalid_embedding_size", "similarity": 0.0}

    emb1 = np.array(live_embedding)
    emb2 = np.array(doc_embedding)

    similarity = float(np.dot(emb1, emb2))

    THRESHOLD = 0.52

    match = similarity >= THRESHOLD

    return {
        "match": match,
        "similarity": round(similarity, 4),
        "threshold": THRESHOLD,
        "note": "similarity ≥ threshold → considered a match",
    }
