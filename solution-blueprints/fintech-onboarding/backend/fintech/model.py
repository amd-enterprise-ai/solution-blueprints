# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os
import urllib.request

import cv2
import numpy as np
from fintech.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("face_model")

MODELS_DIR = os.path.expanduser(os.getenv("FACE_MODELS_DIR", "/facemodels"))

YUNET_URL = "https://huggingface.co/opencv/face_detection_yunet" "/resolve/main/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://huggingface.co/opencv/face_recognition_sface" "/resolve/main/face_recognition_sface_2021dec.onnx"

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")


def _download_if_missing(url: str, path: str):
    if not os.path.exists(path):
        logger.info(f"Downloading {url} → {path}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(url, path)
        logger.info(f"Downloaded OK: {path}")
    else:
        logger.info(f"Model already exists: {path}")


def _enable_opencl():
    if cv2.ocl.haveOpenCL():
        cv2.ocl.setUseOpenCL(True)
        if cv2.ocl.useOpenCL():
            logger.info("OpenCL enabled — models will run on AMD GPU")
            return True
    logger.warning("OpenCL not available — falling back to CPU")
    return False


class FaceApp:
    def __init__(self):
        _download_if_missing(YUNET_URL, YUNET_PATH)
        _download_if_missing(SFACE_URL, SFACE_PATH)

        use_gpu = _enable_opencl()
        target = cv2.dnn.DNN_TARGET_OPENCL if use_gpu else cv2.dnn.DNN_TARGET_CPU

        self.detector = cv2.FaceDetectorYN.create(
            YUNET_PATH,
            "",
            (320, 320),
            score_threshold=0.6,
            nms_threshold=0.3,
            top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=target,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            SFACE_PATH,
            "",
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=target,
        )

        target_str = "AMD GPU (OpenCL)" if use_gpu else "CPU"
        logger.info(f"FaceApp ready: YuNet + SFace on {target_str}")

    def get(self, image_bgr: np.ndarray) -> list:
        h, w = image_bgr.shape[:2]
        self.detector.setInputSize((w, h))

        retval, faces = self.detector.detect(image_bgr)

        if faces is None or len(faces) == 0:
            return []

        result = []
        for face_box in faces:
            aligned = self.recognizer.alignCrop(image_bgr, face_box)
            embedding = self.recognizer.feature(aligned)
            embedding = embedding.flatten()

            face = _FaceResult(
                bbox=face_box[:4],
                det_score=float(face_box[14]),
                embedding=embedding,
            )
            result.append(face)

        return result


class _FaceResult:
    def __init__(self, bbox, det_score, embedding):
        x, y, w, h = bbox[:4]
        self.bbox = np.array([x, y, x + w, y + h], dtype=np.float32)
        self.det_score = det_score
        self.embedding = embedding
        self.age = None
        self.gender = None


face_app = FaceApp()
