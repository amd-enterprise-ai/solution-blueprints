# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import ast
import asyncio
import json
import logging
import os
from typing import Any, Dict, List

import aiohttp

from .schemas import Message

CLASSIFIER_API_KEY = os.getenv("CLASSIFIER_API_KEY", "").strip("\"'").strip()

CLASSIFIER_MODEL_NAME = os.getenv("CLASSIFIER_MODEL_NAME", "").strip("\"'").strip()
CLASSIFIER_LLM_TIMEOUT_SECONDS = float(os.getenv("CLASSIFIER_LLM_TIMEOUT_SECONDS", "15"))
CLASSIFIER_MODEL_DISCOVERY_TIMEOUT_SECONDS = float(os.getenv("CLASSIFIER_MODEL_DISCOVERY_TIMEOUT_SECONDS", "2"))
CLASSIFIER_MODEL_DISCOVERY_MAX_ATTEMPTS = int(os.getenv("CLASSIFIER_MODEL_DISCOVERY_MAX_ATTEMPTS", "8"))

logger = logging.getLogger(__name__)
log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()

logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _sanitize_log(value: str) -> str:
    return str(value).replace("\n", "\\n").replace("\r", "\\r")


class ClassificationLLMClient:
    def __init__(self):
        base_url = os.getenv("CLASSIFIER_BASE_URL", "").strip("\"'").strip()
        if not base_url:
            raise RuntimeError("Set CLASSIFIER_BASE_URL environment variable")
        # Strip trailing slash and remove trailing /v1 so we can append /v1/... once cleanly
        base_url = base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            base_url = "http://" + base_url
        self.api_url = base_url
        logger.info("ClassificationLLMClient base url: %s (api_key set: %s)", self.api_url, bool(CLASSIFIER_API_KEY))
        self.model_name = None
        self._initialized = False
        self.class_descriptions: Dict[str, str] = {}

    async def initialize(self):
        if not self._initialized:
            if CLASSIFIER_MODEL_NAME:
                self.model_name = CLASSIFIER_MODEL_NAME
            else:
                await self._fetch_model_name()
            await self._load_class_descriptions()
            self._initialized = True

    async def _load_class_descriptions(self):
        controller_url = os.getenv("CONTROLLER_URL")
        if not controller_url:
            logger.warning("CONTROLLER_URL not set, will use only class names")
            return

        url = f"{controller_url.rstrip('/')}/config"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        desc_dict: Dict[str, str] = {}
                        for rule in data.get("routing_rules", []):
                            for model in rule.get("models", []):
                                name = model.get("name")
                                desc = model.get("description", "").strip()
                                if name and desc:
                                    desc_dict[name] = desc

                        self.class_descriptions = desc_dict
                        logger.info(f"Loaded {len(self.class_descriptions)} class descriptions from controller")
                    else:
                        logger.warning(f"Failed to load config from {url}, status={resp.status}")
        except Exception as e:
            logger.warning(f"Could not load class descriptions: {e}. Will use only class names.")

    async def _fetch_model_name(self):
        headers = {"Content-Type": "application/json"}
        if CLASSIFIER_API_KEY:
            headers["Authorization"] = f"Bearer {CLASSIFIER_API_KEY}"

        for attempt in range(CLASSIFIER_MODEL_DISCOVERY_MAX_ATTEMPTS):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.api_url}/v1/models",
                        headers=headers,
                        timeout=CLASSIFIER_MODEL_DISCOVERY_TIMEOUT_SECONDS,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data") and len(data["data"]) > 0:
                                self.model_name = data["data"][0]["id"]
                                logger.debug(f"Using model: {self.model_name}")
                                return
                        if resp.status in (401, 403):
                            body = await resp.text()
                            raise RuntimeError(
                                "Classifier model discovery is unauthorized/forbidden "
                                f"(status={resp.status}) at {self.api_url}/v1/models. "
                                "Set CLASSIFIER_MODEL_NAME (or models[].model_name for classifier backend) "
                                "to avoid /v1/models discovery. "
                                f"Response body: {body}"
                            )
                        if resp.status >= 400:
                            body = await resp.text()
                            logger.warning(
                                "Classifier model discovery returned status=%s, body=%s",
                                resp.status,
                                body,
                            )
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)

        raise RuntimeError(
            "Failed to fetch model name from CLASSIFIER_BASE_URL "
            f"after {CLASSIFIER_MODEL_DISCOVERY_MAX_ATTEMPTS} attempts"
        )

    async def classify(
        self,
        messages: List[Message],
        classes: List[str] | None = None,
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        if not self.model_name:
            raise RuntimeError("Model name is not set")

        dialogue = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        logger.debug(f" Dialogue (first 200 chars): {dialogue[:200]}...")

        if classes:
            class_list = []
            for cls in classes:
                desc = self.class_descriptions.get(cls, "").strip()
                if desc:
                    class_list.append(f"{cls}: {desc}")
                else:
                    class_list.append(cls)
            classes_str = "\n".join(f"- {item}" for item in class_list)
        else:
            if self.class_descriptions:
                class_list = [f"{name}: {desc}" for name, desc in self.class_descriptions.items()]
                classes_str = "\n".join(f"- {item}" for item in class_list)
            else:
                classes_str = "No classes provided"
                logger.warning("classify() called without classes and no class_descriptions loaded")

        system_msg = "You are a router classifier. Respond JSON only."
        user_msg = f"""
        You are a routing classifier.

        Given the conversation below, decide which class best describes
        the user's current intent.

        Conversation:
        {dialogue}

        Available classes (with descriptions):
        {classes_str}

        Respond ONLY with valid JSON object:
        {{"class": "exact_class_name_here"}}
        Do not add any explanation, only the JSON.
        """

        logger.debug(f" Sending to LLM model={self.model_name}, api_url={self.api_url}")
        logger.debug(f" User prompt (first 500 chars): {_sanitize_log(user_msg[:500])}...")

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

        timeout = aiohttp.ClientTimeout(total=CLASSIFIER_LLM_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.api_url}/v1/chat/completions",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Classifier API request failed: {resp.status}\n{text}")
                data = await resp.json()

        if not data.get("choices"):
            logger.error(f" No choices in response: {data}")
            return {"class": classes[0] if classes else "Unknown", "confidence": 0.0}

        if not data["choices"][0].get("message"):
            logger.error(f" No message in choice: {data['choices'][0]}")
            return {"class": classes[0] if classes else "Unknown", "confidence": 0.0}

        content = data["choices"][0]["message"].get("content")

        if content is None:
            logger.error("Content is None in response")
            logger.debug(f" Full response: {json.dumps(data, indent=2)}")
            return {"class": classes[0] if classes else "Unknown", "confidence": 0.0}

        logger.debug(f" Classifier raw response content: {content}")

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            try:
                result = ast.literal_eval(content)
            except Exception as e:
                logger.warning(f"Failed to parse model output: {e}")
                result = {"class": classes[0] if classes else "Unknown"}

        logger.debug(f" Selected: {_sanitize_log(str(result.get('class')))} from classes {_sanitize_log(str(classes))}")
        return result
