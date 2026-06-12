# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import base64
import json
import logging
import os
import re
from typing import Any

import aiohttp
import cv2
import numpy as np
from fintech.embedding import extract_embedding_largest_face
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger_docs_front_side = logging.getLogger("docs_front_side")

VLM_TOKEN = os.environ.get("VLM_TOKEN")
if not VLM_TOKEN:
    VLM_TOKEN = "dummy_key"
    logger_docs_front_side.warning("VLM_TOKEN not set or empty - using dummy key")
else:
    logger_docs_front_side.info("VLM_TOKEN is set")

VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://localhost:8000")
vlm_client = OpenAI(base_url=VLM_BASE_URL, api_key=VLM_TOKEN)

VLM_MODEL_NAME = os.getenv("VLM_MODEL_NAME", "").strip("\"'").strip()
VLM_API_KEY = os.getenv("VLM_API_KEY", "")


class VLMClient:
    def __init__(self):
        self.api_url = VLM_BASE_URL
        self.model_name = None
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            if VLM_MODEL_NAME:
                self.model_name = VLM_MODEL_NAME
                logger_docs_front_side.info(f"Using configured model: {self.model_name}")
            else:
                await self._fetch_model_name()
            self._initialized = True

    async def _fetch_model_name(self):
        headers = {"Content-Type": "application/json"}
        if VLM_API_KEY:
            headers["Authorization"] = f"Bearer {VLM_API_KEY}"

        base_url = self.api_url.rstrip("/")

        for attempt in range(120):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{base_url}/models", headers=headers, timeout=1) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data") and len(data["data"]) > 0:
                                self.model_name = data["data"][0]["id"]
                                logger_docs_front_side.info(f"Discovered model: {self.model_name}")
                                return
            except Exception as e:
                logger_docs_front_side.warning(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)

        raise RuntimeError("Failed to fetch model name from VLM_BASE_URL")


# Create global instance
vlm_client_instance = VLMClient()


async def ensure_vlm_initialized():
    await vlm_client_instance.initialize()
    return vlm_client_instance.model_name


async def user_data_front_side(file) -> dict[str, bool | Any]:
    logger_docs_front_side.info("==== VLM document parsing started ====")

    model_name = await ensure_vlm_initialized()
    logger_docs_front_side.info(f"Using VLM model: {model_name}")

    data = await file.read()
    logger_docs_front_side.info(f"Received file size: {len(data)} bytes")

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    if img is None:
        logger_docs_front_side.error("Image decode failed")
        return {"success": False, "reason": "invalid_image"}

    emb_result = extract_embedding_largest_face(img)
    if not emb_result.get("success"):
        logger_docs_front_side.error("Embedding extraction failed")
        return {"success": False, "reason": emb_result.get("reason")}

    logger_docs_front_side.info("Embedding extracted successfully")

    # ---- Encode image ----
    image_base64 = base64.b64encode(data).decode()
    logger_docs_front_side.info(f"Base64 image length: {len(image_base64)} characters")

    try:
        logger_docs_front_side.info(f"Sending request to VLM model: {model_name}")

        completion = vlm_client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a strict JSON generator."},
                {
                    "role": "system",
                    "content": "You are a strict JSON generator. You output ONLY valid JSON, no explanations, no markdown, no code blocks.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
                You are analyzing a US DRIVING LICENSE. Different states have different formats.
                Your task: extract the person's identity information regardless of format.

                KEY FIELDS TO IDENTIFY:

                1. SURNAME/LAST NAME:
                   - Look for: "LN", "Last Name", "Surname", "1.", or any field ending with name
                   - Often appears near "FN", "Given Names", or first name

                2. FIRST NAME/GIVEN NAME:
                   - Look for: "FN", "Given Names", "First Name", "2."

                3. DATE OF BIRTH:
                   - Look for: "DOB", "Birth", "3."
                   - US Driver's Licenses ALWAYS use MM/DD/YYYY format. NEVER DD/MM/YYYY.
                   - Example: "01/05/1975" means January 5th, 1975 → output "1975-01-05"
                   - Example: "12/25/1990" means December 25th, 1990 → output "1990-12-25"
                   - The first number is ALWAYS the month (1-12), second is ALWAYS the day (1-31)

                4. GENDER/SEX:
                   - Look for: "SEX", "Sex:", "4.", "M", "F"
                   - Often a single letter: M or F

                Return ONLY valid JSON with this schema:
                {
                  "surname": string or null,
                  "name": string or null,
                  "gender": "male" or "female" or null,
                  "dateOfBirth": "YYYY-MM-DD" or null
                }

                EXTRACTION RULES:
                - Convert all dates to YYYY-MM-DD format
                - If you see "M" or "MALE" → gender = "male"
                - If you see "F" or "FEMALE" → gender = "female"
                - If multiple names appear, surname is usually the family name, name is the given name
                - Preserve original capitalization of names
                - If you're unsure about surname vs name, use your best judgment based on context
                - Dates on US licenses are MM/DD/YYYY. "01/05/1973" → month=01, day=05 → "1973-01-05"
                - NEVER interpret the first number as a day. It is ALWAYS the month.

                IMPORTANT: Your response must be PURE JSON, NOT inside markdown code blocks.
                Example of correct response:
                {"surname": "SMITH", "name": "JOHN", "gender": "male", "dateOfBirth": "1980-01-01"}

                Incorrect (DO NOT DO THIS):
                ```json
                {"surname": "SMITH", ...}

                Now analyze this driving license image and extract the information:
                """,
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                },
            ],
        )

        logger_docs_front_side.info("VLM response received")

        raw_output = completion.choices[0].message.content.strip()
        logger_docs_front_side.info(f"Raw VLM output length: {len(raw_output)}")
        logger_docs_front_side.info(f"Raw VLM output preview: {raw_output[:300]}")

        if "```" in raw_output:
            logger_docs_front_side.warning("Markdown detected in VLM output, cleaning")

            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_output)
            if json_match:
                raw_output = json_match.group(1).strip()
                logger_docs_front_side.info("Extracted JSON from code block")
            else:
                raw_output = re.sub(r"```json|```", "", raw_output).strip()

        raw_output = re.sub(r"^json\s*", "", raw_output, flags=re.IGNORECASE).strip()

        logger_docs_front_side.info(f"Cleaned output for parsing: {raw_output[:100]}")

        try:
            user_data = json.loads(raw_output)
            logger_docs_front_side.info("JSON parsed successfully")
        except json.JSONDecodeError as e:
            logger_docs_front_side.error(f"JSON decode error: {e}")
            logger_docs_front_side.error(f"Problem string: {repr(raw_output)}")
            raise

    except Exception as e:
        logger_docs_front_side.exception("VLM parsing error occurred")
        return {"success": False, "reason": "vlm_parse_error"}

    logger_docs_front_side.info("==== VLM document parsing SUCCESS ====")

    return {"success": True, "embedding": emb_result["embedding"], "user_data": user_data}
