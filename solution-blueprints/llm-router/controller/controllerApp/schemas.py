# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import List, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str


class LlmRouterInfo(BaseModel):
    policy: str
    routing_strategy: str
    model: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    llm_router: LlmRouterInfo = Field(..., alias="llm-router")
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None


class ErrorModel(BaseModel):
    error: dict
