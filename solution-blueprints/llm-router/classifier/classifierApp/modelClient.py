# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import ast
import asyncio
import json
import os
from typing import Any, Dict, List, Sequence

import aiohttp

from .schemas import Message

CLASSIFIER_BASE_URL = os.getenv("CLASSIFIER_BASE_URL", "").strip("\"'").strip()
if not CLASSIFIER_BASE_URL:
    raise RuntimeError("Set CLASSIFIER_BASE_URL environment variable")

CLASSIFIER_API_KEY = os.getenv("CLASSIFIER_API_KEY", "").strip("\"'").strip()

CLASSIFIER_MODEL_NAME = os.getenv("CLASSIFIER_MODEL_NAME", "").strip("\"'").strip()


class ClassificationLLMClient:
    def __init__(self):
        self.api_url = CLASSIFIER_BASE_URL
        self.model_name = None
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            if CLASSIFIER_MODEL_NAME:
                self.model_name = CLASSIFIER_MODEL_NAME
            else:
                await self._fetch_model_name()
            self._initialized = True

    async def _fetch_model_name(self):
        headers = {"Content-Type": "application/json"}
        if CLASSIFIER_API_KEY:
            headers["Authorization"] = f"Bearer {CLASSIFIER_API_KEY}"

        for attempt in range(120):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_url}/v1/models", headers=headers, timeout=1) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data") and len(data["data"]) > 0:
                                self.model_name = data["data"][0]["id"]
                                print(f"[DEBUG] Using model: {self.model_name}")
                                return
            except Exception as e:
                print(f"[WARN] Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)

        raise RuntimeError("Failed to fetch model name from CLASSIFIER_BASE_URL")

    async def classify(
        self,
        messages: Sequence[Message],
        classes: List[str],
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        if not self.model_name:
            raise RuntimeError("Model name is not set")

        dialogue = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)

        system_msg = "You are a router classifier. Respond JSON only."
        user_msg = f"""
        You are a routing classifier.

        Given the conversation below, decide which class best describes
        the user's current intent.

        Conversation:
        {dialogue}

        Classes:
        {classes}

        Respond ONLY with valid JSON:
        {{"class": "<one_of_classes>"}}
        """

        body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 128,
            "temperature": 0.0,
        }

        headers = {"Content-Type": "application/json"}
        if CLASSIFIER_API_KEY:
            headers["Authorization"] = f"Bearer {CLASSIFIER_API_KEY}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/v1/chat/completions",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Classifier API request failed: {resp.status}\n{text}")
                data = await resp.json()

        content = data["choices"][0]["message"]["content"]
        print(f"[DEBUG] Classifier raw response content: {content}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(content)
            except Exception as e:
                print(f"[WARN] Failed to parse model output: {e}")
                return {"class": None}
