# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from fintech.embedding import extract_embedding

logging.basicConfig(level=logging.INFO)
logger_liveness = logging.getLogger("liveness")

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)


async def get_liveness_embeddings(files: list[Any]) -> dict[str, bool | dict[str, bool | int] | Any]:
    yaw_left_detected = False
    yaw_right_detected = False
    blink_detected = False

    STATE_YAW_LEFT = 0
    STATE_YAW_RIGHT = 1
    STATE_BLINK = 2
    STATE_DONE = 3

    state = STATE_YAW_LEFT
    embeddings = []

    EAR_THRESHOLD = 0.2

    logger_liveness.info("==== Liveness check started ====")
    logger_liveness.info(f"Total frames received: {len(files)}")

    frame_index = 0

    for file in files:
        frame_index += 1
        logger_liveness.info(f"--- Frame {frame_index} --- Current state: {state}")

        data = await file.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

        if img is None:
            logger_liveness.warning("Image decode failed")
            continue

        # --- InsightFace embedding ---
        result = extract_embedding(img)
        if not result.get("success"):
            logger_liveness.warning("Embedding extraction failed")
            continue

        embeddings.append(np.array(result["embedding"]))
        logger_liveness.info(f"Embedding extracted. Total embeddings: {len(embeddings)}")

        # --- MediaPipe landmarks ---
        img_h, img_w = img.shape[:2]
        rgb_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_result = face_mesh.process(rgb_frame)

        if not mp_result.multi_face_landmarks:
            logger_liveness.warning("No face landmarks detected")
            continue

        landmarks = mp_result.multi_face_landmarks[0].landmark
        yaw = get_yaw(landmarks, img_w, img_h)

        logger_liveness.info(f"Yaw detected: {yaw:.2f}")

        # --- State machine ---
        if state == STATE_YAW_LEFT:
            if yaw < -10:
                logger_liveness.info("YAW LEFT detected")
                yaw_left_detected = True
                state = STATE_YAW_RIGHT

        elif state == STATE_YAW_RIGHT:
            if yaw > 10:
                logger_liveness.info("YAW RIGHT detected")
                yaw_right_detected = True
                state = STATE_BLINK

        elif state == STATE_BLINK:
            left_eye = [landmarks[i] for i in [33, 160, 158, 133, 153, 144]]
            right_eye = [landmarks[i] for i in [263, 387, 385, 362, 380, 373]]

            ear_left = eye_aspect_ratio(left_eye, img_w, img_h)
            ear_right = eye_aspect_ratio(right_eye, img_w, img_h)

            logger_liveness.info(f"EAR left: {ear_left:.3f}, EAR right: {ear_right:.3f}")

            if ear_left < EAR_THRESHOLD or ear_right < EAR_THRESHOLD:
                logger_liveness.info("BLINK detected")
                blink_detected = True
                state = STATE_DONE

    logger_liveness.info(f"Final state: {state}")
    logger_liveness.info(f"Total embeddings collected: {len(embeddings)}")

    liveness_details = {
        "yaw_left_detected": yaw_left_detected,
        "yaw_right_detected": yaw_right_detected,
        "blink_detected": blink_detected,
        "final_state": state,
        "challenge_passed": state == STATE_DONE,
    }

    if state != STATE_DONE:
        logger_liveness.warning("❌ Challenge not passed")
        logger_liveness.info("==== Liveness summary ====")
        logger_liveness.info(f"Yaw left detected: {yaw_left_detected}")
        logger_liveness.info(f"Yaw right detected: {yaw_right_detected}")
        logger_liveness.info(f"Blink detected: {blink_detected}")

        return {
            "success": False,
            "reason": "challenge_not_passed",
            "embedding": None,
            "liveness_details": liveness_details,
        }

    if len(embeddings) == 0:
        logger_liveness.warning("❌ No embeddings collected")
        return {"success": False, "reason": "no_embeddings", "embedding": None, "liveness_details": liveness_details}

    avg_embedding = np.mean(embeddings, axis=0)
    avg_embedding /= np.linalg.norm(avg_embedding)

    logger_liveness.info("Liveness SUCCESS!!!")

    return {"success": True, "embedding": avg_embedding.tolist(), "liveness_details": liveness_details}


def get_yaw(landmarks, img_w, img_h):
    left_eye = np.array([landmarks[33].x * img_w, landmarks[33].y * img_h])
    right_eye = np.array([landmarks[263].x * img_w, landmarks[263].y * img_h])
    nose_tip = np.array([landmarks[1].x * img_w, landmarks[1].y * img_h])
    eye_center = (left_eye + right_eye) / 2
    dx = nose_tip[0] - eye_center[0]
    face_width = np.linalg.norm(right_eye - left_eye)
    yaw_deg = np.degrees(np.arctan2(dx, face_width))
    return yaw_deg


def eye_aspect_ratio(eye_landmarks, img_w, img_h):
    p1 = np.array([eye_landmarks[0].x * img_w, eye_landmarks[0].y * img_h])
    p2 = np.array([eye_landmarks[1].x * img_w, eye_landmarks[1].y * img_h])
    p3 = np.array([eye_landmarks[2].x * img_w, eye_landmarks[2].y * img_h])
    p4 = np.array([eye_landmarks[3].x * img_w, eye_landmarks[3].y * img_h])
    p5 = np.array([eye_landmarks[4].x * img_w, eye_landmarks[4].y * img_h])
    p6 = np.array([eye_landmarks[5].x * img_w, eye_landmarks[5].y * img_h])
    ear = (np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2 * np.linalg.norm(p1 - p4))
    return ear
