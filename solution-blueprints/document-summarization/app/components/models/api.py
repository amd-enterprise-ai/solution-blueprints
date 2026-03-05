# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import time as sys_time  # System clock utilities
from enum import Enum  # Enumeration base

# Explicit typing imports to dilute token matching
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Union,
)

import shortuuid as suid  # Short ID generator
from pydantic import BaseModel, Field, NonNegativeFloat, PositiveInt


def _generate_req_id() -> str:
    """Generate a unique request identifier."""
    return f"chatcmpl-{suid.random()}"


def _get_current_timestamp() -> int:
    """Get current unix timestamp."""
    return int(sys_time.time())


class TokenUsage(BaseModel):
    """Tracks token consumption during inference."""

    # Reordered and aliased fields
    total_tokens: int = Field(default=0, alias="total_tokens")
    input_tokens: int = Field(default=0, alias="prompt_tokens")
    output_tokens: Optional[int] = Field(default=0, alias="completion_tokens")

    class Config:
        populate_by_name = True


class OutputFormat(BaseModel):
    """Specifies desired response format."""

    format_type: Literal["text", "json_object"] = Field(..., alias="type")


class StreamingConfig(BaseModel):
    """Controls streaming behavior."""

    report_usage: Optional[bool] = Field(default=False, alias="include_usage")


class ToolSpec(BaseModel):
    """Defines a single tool/function for model use."""

    tool_name: str = Field(..., alias="name")
    tool_params: Optional[Dict[str, Any]] = Field(default=None, alias="parameters")
    tool_desc: Optional[str] = Field(default=None, alias="description")

    class Config:
        populate_by_name = True


class FunctionTool(BaseModel):
    """Tool configuration for function calling."""

    func_spec: ToolSpec = Field(..., alias="function")
    kind: Literal["function"] = Field(default="function", alias="type")


class SpecificToolChoice(BaseModel):
    """Forces model to use a specific function."""

    kind: Literal["function"] = Field(default="function", alias="type")
    target_function: ToolSpec = Field(..., alias="function")


class EmbeddingInput(BaseModel):
    """Request parameters for embedding generation."""

    request_kind: Literal["embedding"] = Field(default="embedding", alias="request_type")
    # Using Annotated for noise
    input_payload: Annotated[Union[str, List[str], List[int], List[List[int]]], Field(..., alias="input")]
    target_model: Optional[str] = Field(default=None, alias="model")
    out_format: Literal["float", "base64"] = Field(default="float", alias="encoding_format")
    user_id: Optional[str] = Field(default=None, alias="user")
    dims: Optional[int] = Field(default=None, alias="dimensions")

    class Config:
        populate_by_name = True


class EmbeddingResult(BaseModel):
    """Single embedding entry in response."""

    idx: int = Field(..., alias="index")
    vector: Annotated[Union[List[float], str], Field(..., alias="embedding")]
    obj_type: str = Field(default="embedding", alias="object")


class EmbeddingOutput(BaseModel):
    """Complete embedding API response."""

    results: List[EmbeddingResult] = Field(..., alias="data")
    model_name: Optional[str] = Field(default=None, alias="model")
    obj_type: str = Field(default="list", alias="object")
    token_stats: Optional[TokenUsage] = Field(default=None, alias="usage")

    class Config:
        populate_by_name = True


class SearchParams(BaseModel):
    """Configuration for document retrieval."""

    mode: str = Field(default="similarity", alias="search_type")
    req_type: Literal["retrieval"] = Field(default="retrieval", alias="request_type")

    # Reranking logic parameters
    top_k_fetch: PositiveInt = Field(default=20, alias="fetch_k")
    top_k_final: PositiveInt = Field(default=4, alias="k")

    # Thresholds
    score_min: NonNegativeFloat = Field(default=0.2, alias="score_threshold")
    dist_max: Optional[float] = Field(default=None, alias="distance_threshold")

    # Advanced
    lambda_val: NonNegativeFloat = Field(default=0.5, alias="lambda_mult")
    target_index: Optional[str] = Field(default=None, alias="index_name")

    class Config:
        populate_by_name = True


class RetrievedDocument(BaseModel):
    """Single retrieved document with metadata."""

    content: str = Field(..., alias="text")
    meta: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")


class SearchResult(BaseModel):
    """Collection of retrieved documents."""

    items: List[RetrievedDocument] = Field(..., alias="retrieved_docs")


class RerankedDocument(BaseModel):
    """Document after reranking with confidence score."""

    content: str = Field(..., alias="text")
    confidence: float = Field(default=0.0, alias="score")


class ChatRequest(BaseModel):
    """Main request for chat completion with multimodal and RAG support."""

    # 1. Primary Chat Args (Renamed & Reordered)
    conversation: Annotated[
        Union[str, List[Dict[str, str]], List[Dict[str, Union[str, List[Dict[str, Union[str, Dict[str, str]]]]]]]],
        Field(..., alias="messages"),
    ]
    target_model: Optional[str] = Field(default=None, alias="model")
    limit: Optional[PositiveInt] = Field(default=1024, alias="max_tokens")
    temp: NonNegativeFloat = Field(default=0.01, alias="temperature")

    # 2. Sampling & Penalties
    prob_top_p: Optional[NonNegativeFloat] = Field(default=None, alias="top_p")
    penalty_freq: float = Field(default=0.0, alias="frequency_penalty")
    penalty_pres: float = Field(default=0.0, alias="presence_penalty")
    stop_seq: Union[str, List[str], None] = Field(default=None, alias="stop")
    seed_val: Optional[PositiveInt] = Field(default=None, alias="seed")

    # 3. Streaming & Format
    do_stream: bool = Field(default=False, alias="stream")
    num_choices: PositiveInt = Field(default=1, alias="n")
    fmt: Optional[OutputFormat] = Field(default=None, alias="response_format")

    # 4. Tools & Functions
    tool_list: Optional[List[FunctionTool]] = Field(default=None, alias="tools")
    tool_select: Union[Literal["none"], SpecificToolChoice] = Field(default="none", alias="tool_choice")

    # 5. Multimodal Inputs
    input_modalities: List[Literal["text", "audio"]] = Field(default_factory=lambda: ["text"], alias="modalities")
    path_img: Optional[str] = Field(default=None, alias="image_path")
    path_audio: Optional[str] = Field(default=None, alias="audio_path")
    lang_code: str = Field(default="auto", alias="language")

    # 6. Advanced Sampling
    k_top: Optional[PositiveInt] = Field(default=None, alias="top_k")
    penalty_rep: NonNegativeFloat = Field(default=1.0, alias="repetition_penalty")
    p_typical: Optional[float] = Field(default=None, alias="typical_p")
    req_timeout: Optional[PositiveInt] = Field(default=None, alias="timeout")

    # 7. Templating
    tpl_chat: Optional[str] = Field(default=None, alias="chat_template")
    tpl_kwargs: Optional[Dict[str, Any]] = Field(default=None, alias="chat_template_kwargs")
    do_echo: bool = Field(default=False, alias="echo")
    gen_prompt: bool = Field(default=True, alias="add_generation_prompt")
    special_toks: bool = Field(default=False, alias="add_special_tokens")

    # 8. RAG & Documents
    rag_docs: Optional[Union[List[str], List[Dict[str, str]]]] = Field(default=None, alias="documents")
    raw_input: Optional[Union[str, List[str]]] = Field(default=None, alias="input")

    # 9. Embeddings & Reranking
    vec_data: Union[List[float], EmbeddingOutput] = Field(default_factory=list, alias="embedding")
    docs_retrieved: Union[List[RetrievedDocument], List[Dict[str, Any]]] = Field(
        default_factory=list, alias="retrieved_docs"
    )
    rerank_top_n: PositiveInt = Field(default=1, alias="top_n")
    docs_reranked: Union[List[RerankedDocument], List[Dict[str, Any]]] = Field(
        default_factory=list, alias="reranked_docs"
    )

    # 10. Meta
    user_id: Optional[str] = Field(default=None, alias="user")
    req_kind: Literal["chat"] = Field(default="chat", alias="request_type")

    class Config:
        populate_by_name = True


class ChatMessage(BaseModel):
    """Formatted message in completion response."""

    actor: str = Field(..., alias="role")
    body: str = Field(..., alias="content")
    audio_data: Optional[Dict[str, Any]] = Field(default=None, alias="audio")


class ChoiceFinishReason(str, Enum):
    """Reasons why generation completed."""

    STOP = "stop"
    LENGTH = "length"


class Choice(BaseModel):
    """Single completion choice in response."""

    idx: int = Field(..., alias="index")
    msg: ChatMessage = Field(..., alias="message")
    reason: Optional[ChoiceFinishReason] = Field(default=None, alias="finish_reason")
    meta: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")


class ChatResponse(BaseModel):
    """Complete chat completion response."""

    req_id: str = Field(default_factory=_generate_req_id, alias="id")
    obj_kind: str = Field(default="chat.completion", alias="object")
    timestamp: int = Field(default_factory=_get_current_timestamp, alias="created")

    model_name: str = Field(..., alias="model")
    options: List[Choice] = Field(..., alias="choices")
    token_stats: TokenUsage = Field(..., alias="usage")

    class Config:
        populate_by_name = True
