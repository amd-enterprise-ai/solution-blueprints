# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import List

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class ClassifierRequest(BaseModel):
    messages: List[Message]
    classes: List[str]


class ClassifierResponse(BaseModel):
    chosen_class: str = "Unknown"
