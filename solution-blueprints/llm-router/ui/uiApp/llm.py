# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging

from openai import OpenAI

logger = logging.getLogger("LLM_Client")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)


class Router:
    def __init__(self, base_url):
        self.api = OpenAI(api_key="not-required", max_retries=0, timeout=120.0)
        self.api.base_url = base_url

    def predict(self, prompt_text, conversation, routing_mode, policy_name, model_name):
        logger.info("Predict called")
        logger.info(f"Prompt: {prompt_text}")
        logger.info(f"Conversation history: {conversation}")

        previous_messages = []
        for user_msg, meta_message in conversation:
            meta_message = meta_message.split("] ", maxsplit=1)[-1]
            previous_messages.append({"role": "user", "content": user_msg})
            previous_messages.append({"role": "assistant", "content": meta_message})

        previous_messages.append({"role": "user", "content": prompt_text})
        logger.debug(f"History for API: {previous_messages}")

        context = {"llm-router": {"routing_strategy": routing_mode}}
        if policy_name:
            context["llm-router"]["policy"] = policy_name
        if routing_mode == "manual" and model_name:
            context["llm-router"]["model"] = model_name

        logger.debug(f"Extra body: {context}")

        try:
            answer = self.api.chat.completions.with_raw_response.create(
                model="",
                messages=previous_messages,
                temperature=0.5,
                top_p=1,
                max_tokens=2048,
                stream=True,
                stream_options={"include_usage": True},
                extra_body=context,
            )
        except Exception as exc:
            logger.exception("API call failed")

            error_details = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

            if hasattr(exc, "response") and exc.response is not None:
                error_details["status_code"] = getattr(exc.response, "status_code", None)
                try:
                    error_details["response"] = exc.response.text
                except Exception as resp_exc:
                    logger.debug("Failed to read error response body: %s", resp_exc)
                    error_details.setdefault("response_unavailable", True)

            formatted = "\n".join(f"**{k}**: `{v}`" for k, v in error_details.items() if v)

            yield ("<span style='color:#ff4d4f; font-weight:600;'>" "❌ Request failed</span>\n\n" f"{formatted}")
            return

        current_class = answer.headers.get("X-Chosen-Classifier")
        if current_class:
            logger.info(f"Classifier selected: {current_class}")

        accumulated = ""
        model_used = None

        for chunk in answer.parse():
            if chunk.choices and hasattr(chunk.choices[0], "delta"):
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    if model_used is None:
                        model_used = chunk.model
                        logger.info(f"Model in use: {model_used}")
                    accumulated += content
                    yield f"[**{model_used}**|{current_class}] {accumulated}"
