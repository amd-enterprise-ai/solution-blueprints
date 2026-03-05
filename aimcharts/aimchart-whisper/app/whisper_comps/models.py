# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import BaseModel


class SpeechRecognitionResult(BaseModel):
    """Response schema for audio-to-text conversion."""

    text: str  # Transcribed speech content
