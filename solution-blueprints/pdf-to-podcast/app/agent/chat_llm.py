# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Generic OpenAI-compatible chat wrapper (text + vision, tools, structured output)."""
import base64
import enum
import logging
import os
import warnings
from typing import Any, AsyncIterator, Iterator, Sequence, TypeVar, cast

import httpx
from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.output_parsers import (
    BaseOutputParser,
    JsonOutputParser,
    PydanticOutputParser,
)
from langchain_core.outputs import (
    ChatGeneration,
    ChatGenerationChunk,
    ChatResult,
    Generation,
)
from langchain_core.runnables import Runnable
from langchain_core.utils.pydantic import is_basemodel_subclass
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T_Parser = TypeVar("T_Parser", bound=BaseOutputParser)


class ChatLLM(BaseChatModel):
    """Lightweight OpenAI-compatible chat model wrapper.

    This adapter mirrors the OpenAI chat/completions API for text, vision, tools,
    and structured output so it can target any compatible endpoint (e.g., vLLM).
    Configuration is provided via model/base_url/api_key and optional OpenAI-style
    tuning parameters (temperature, max_tokens, top_p, stop).
    """

    model: str
    base_url: str
    api_key: str | None = None
    temperature: float | None = 0.0
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    timeout: float = 150.0

    @property
    def _llm_type(self) -> str:  # pragma: no cover - required by BaseChatModel
        """Identifier used by LangChain to label this LLM implementation."""
        return "chat-llm"

    # ------------------------------------------------------------------ #
    # Payload helpers
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        """Build auth headers for the target endpoint."""
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    @staticmethod
    def _is_url(value: str) -> bool:
        """Check whether a string is a valid URL with scheme and host."""
        try:
            url = httpx.URL(value)
            return bool(url.scheme and url.host)
        except Exception:
            return False

    @classmethod
    def _to_data_url(cls, image_source: str) -> str:
        """Normalize an image reference to a URL or data URI.

        Args:
            image_source: HTTP(S) URL, data URI, or local filesystem path.

        Returns:
            A URL or data URI that downstream HTTP clients can consume.

        Raises:
            ValueError: If the value cannot be resolved to a valid image source.
        """
        if image_source.startswith("data:image"):
            return image_source

        if cls._is_url(image_source):
            return image_source

        if os.path.exists(image_source):
            with open(image_source, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"

        msg = "Image source must be an http(s) URL, data URI, or existing file path"
        raise ValueError(msg)

    @classmethod
    def _convert_messages(cls, messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
        """Convert LangChain messages into OpenAI-compatible payload objects."""
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = (
                "user" if isinstance(message, HumanMessage) else "assistant" if message.type == "ai" else message.type
            )

            if isinstance(message, ToolMessage):
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": message.content,
                    }
                )
                continue

            content = message.content
            if isinstance(message, HumanMessage) and isinstance(content, list):
                normalized = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image_url":
                        url = block["image_url"]["url"]
                        normalized.append({"type": "image_url", "image_url": {"url": cls._to_data_url(url)}})
                    else:
                        normalized.append(block)
                converted.append({"role": role, "content": normalized})
            else:
                converted.append({"role": role, "content": content})
        return converted

    def _build_payload(
        self,
        messages: Sequence[BaseMessage],
        stop: list[str] | None = None,
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Compose an OpenAI-style request payload."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if stop:
            payload["stop"] = stop
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return payload

    # ------------------------------------------------------------------ #
    # Response parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_tool_calls(raw_tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Normalize OpenAI tool_calls into LangChain ToolCall objects."""
        tool_calls: list[ToolCall] = []
        for tc in raw_tool_calls:
            if tc.get("type") != "function":
                continue
            func = tc.get("function") or {}
            tool_calls.append(
                {
                    "id": tc.get("id"),
                    "name": func.get("name"),
                    "args": func.get("arguments") or {},
                    "type": "tool_call",
                }
            )
        return tool_calls

    def _chat_result_from_response(self, data: dict[str, Any]) -> ChatResult:
        """Translate an OpenAI-style response JSON into a LangChain ChatResult."""
        choice = data["choices"][0]
        message_dict = choice["message"]
        tool_calls = self._parse_tool_calls(message_dict.get("tool_calls") or [])

        ai_message = AIMessage(
            content=message_dict.get("content", "") or "",
            tool_calls=tool_calls,
            additional_kwargs=message_dict.get("function_call") or {},
            response_metadata={"finish_reason": choice.get("finish_reason")},
        )
        generation = ChatGeneration(message=ai_message, generation_info={"finish_reason": choice.get("finish_reason")})
        llm_output = {
            "token_usage": data.get("usage"),
            "model": data.get("model"),
        }
        return ChatResult(generations=[generation], llm_output=llm_output)

    # ------------------------------------------------------------------ #
    # Sync
    # ------------------------------------------------------------------ #
    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous chat completion request."""
        payload = self._build_payload(messages, stop=stop, **kwargs)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        return self._chat_result_from_response(data)

    def _stream(
        self,
        messages: Sequence[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Synchronous streaming chat completion."""
        payload = self._build_payload(messages, stop=stop, stream=True, **kwargs)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=None) as client:
            with client.stream("POST", url, json=payload, headers=self._headers()) as r:
                yield from self._iter_stream(r.iter_lines(), run_manager)

    # ------------------------------------------------------------------ #
    # Async
    # ------------------------------------------------------------------ #
    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async chat completion request."""
        payload = self._build_payload(messages, stop=stop, **kwargs)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        return self._chat_result_from_response(data)

    async def _astream(
        self,
        messages: Sequence[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Async streaming chat completion."""
        payload = self._build_payload(messages, stop=stop, stream=True, **kwargs)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as r:
                async for chunk in self._aiter_stream(r.aiter_lines(), run_manager):
                    yield chunk

    @classmethod
    def _create_thinking_aware_parser(cls, base_parser_class: type[T_Parser]) -> type[T_Parser]:
        """Wrap a parser to drop any <think>... </think> preamble before parsing."""

        class ThinkingAwareParser(base_parser_class):  # type: ignore[valid-type,misc]
            def parse(self, text: str) -> Any:
                actual_content = self._extract_content_after_thinking(text)
                return super().parse(actual_content)

            def parse_result(self, result: list[Generation], *, partial: bool = False) -> Any:
                if result and hasattr(result[0], "text"):
                    original_text = result[0].text
                    actual_content = self._extract_content_after_thinking(original_text)
                    clean_generation = Generation(text=actual_content, generation_info=result[0].generation_info)
                    clean_result = [clean_generation] + result[1:]
                    return super().parse_result(clean_result, partial=partial)
                return super().parse_result(result, partial=partial)

            @staticmethod
            def _extract_content_after_thinking(content: str) -> str:
                """Strip leading <think> sections (if present) before returning text."""
                if content and "<think>" in content and "</think>" in content:
                    think_end = content.rfind("</think>")
                    if think_end != -1:
                        return content[think_end + len("</think>") :].strip()
                return content

        return cast(type[T_Parser], ThinkingAwareParser)

    def with_structured_output(  # type: ignore[override]
        self,
        schema: dict[str, Any] | type,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict | BaseModel]:
        """Bind schema-aware structured output parsing.

        Args:
            schema: JSON schema dict, Enum subclass, or Pydantic BaseModel subclass.
            include_raw: Not supported; kept for API parity.

        Returns:
            A runnable that produces parsed structured outputs according to `schema`.

        Raises:
            ValueError: If `schema` type is unsupported.
            NotImplementedError: When include_raw is requested.
        """
        if "method" in kwargs:
            warnings.warn("`method` is ignored; parser is chosen by schema type.")
            kwargs.pop("method", None)

        if kwargs.get("strict", True) is not True:
            warnings.warn("`strict` is ignored; parsing is best-effort.")

        if include_raw:
            msg = "include_raw=True is not supported in this adapter."
            raise NotImplementedError(msg)

        guided_schema: dict[str, Any] | Any = schema

        if isinstance(schema, dict):
            ThinkingAwareJsonOutputParser = self._create_thinking_aware_parser(JsonOutputParser)
            output_parser: BaseOutputParser = ThinkingAwareJsonOutputParser()
        elif isinstance(schema, type) and issubclass(schema, enum.Enum):

            class EnumOutputParser(BaseOutputParser):
                enum: type[enum.Enum]

                def parse(self, response: str) -> Any:
                    try:
                        return self.enum(response.strip())
                    except ValueError:
                        return None

            choices = [choice.value for choice in schema]
            if not all(isinstance(choice, str) for choice in choices):
                raise ValueError("Enum schema must only contain string choices.")

            ThinkingAwareEnumOutputParser = self._create_thinking_aware_parser(EnumOutputParser)
            output_parser = ThinkingAwareEnumOutputParser(enum=schema)
            guided_schema = choices

        elif is_basemodel_subclass(schema):

            class ForgivingPydanticOutputParser(PydanticOutputParser):
                def parse_result(self, result: list[Generation], *, partial: bool = False) -> Any:
                    try:
                        return super().parse_result(result, partial=partial)
                    except OutputParserException:
                        return None

            ThinkingAwarePydanticOutputParser = self._create_thinking_aware_parser(ForgivingPydanticOutputParser)
            output_parser = ThinkingAwarePydanticOutputParser(pydantic_object=schema)

            if hasattr(schema, "model_json_schema"):
                guided_schema = schema.model_json_schema()
            else:
                guided_schema = schema.schema()  # type: ignore[attr-defined]

        else:
            msg = "Schema must be a dict (JSON schema), Enum, or Pydantic BaseModel subclass."
            raise ValueError(msg)

        ls_structured_output_format = {"schema": guided_schema}

        return super().bind(ls_structured_output_format=ls_structured_output_format, **kwargs) | output_parser

    # ------------------------------------------------------------------ #
    # Internal stream helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_stream_choice(choice: dict[str, Any]) -> ChatGenerationChunk | None:
        """Convert a streaming choice delta into a ChatGenerationChunk, if any."""
        delta = choice.get("delta") or {}
        content_piece = delta.get("content") or ""
        tool_calls_chunk = delta.get("tool_calls") or []

        tool_call_chunks = []
        for tc in tool_calls_chunk:
            if tc.get("type") != "function":
                continue
            func = tc.get("function") or {}
            tool_call_chunks.append(
                {
                    "id": tc.get("id"),
                    "name": func.get("name"),
                    "args": func.get("arguments"),
                    "index": tc.get("index"),
                }
            )

        if not content_piece and not tool_call_chunks:
            return None

        ai_chunk = AIMessageChunk(
            content=content_piece,
            tool_call_chunks=tool_call_chunks,  # type: ignore[arg-type]
            response_metadata={"finish_reason": choice.get("finish_reason")},
        )
        return ChatGenerationChunk(message=ai_chunk)

    def _iter_stream(
        self, lines: Iterator[bytes], run_manager: CallbackManagerForLLMRun | None
    ) -> Iterator[ChatGenerationChunk]:
        """Yield sync stream chunks from an httpx byte-iterator."""
        for line in lines:
            if not line:
                continue
            chunk_json = line.removeprefix(b"data: ")
            if chunk_json == line:
                continue
            if chunk_json.strip() == b"[DONE]":
                continue
            chunk = httpx.Response(200, content=chunk_json).json()
            choice = chunk["choices"][0]
            gen_chunk = self._parse_stream_choice(choice)
            if gen_chunk is None:
                continue
            if run_manager:
                run_manager.on_llm_new_token(gen_chunk.message.content, chunk=gen_chunk)
            yield gen_chunk

    async def _aiter_stream(
        self,
        lines: AsyncIterator[str],
        run_manager: AsyncCallbackManagerForLLMRun | None,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Yield async stream chunks from an async line iterator."""
        async for line in lines:

            if not line:
                continue

            chunk_json = line.removeprefix("data: ")
            if chunk_json == line:
                continue
            if chunk_json.strip() == "[DONE]":
                continue
            chunk = httpx.Response(200, content=chunk_json).json()
            choice = chunk["choices"][0]
            gen_chunk = self._parse_stream_choice(choice)

            if gen_chunk is None:
                continue

            if run_manager:
                await run_manager.on_llm_new_token(gen_chunk.message.content, chunk=gen_chunk)

            yield gen_chunk
