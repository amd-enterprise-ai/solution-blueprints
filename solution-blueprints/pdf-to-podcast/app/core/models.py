# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Shared models and enums used across the service."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

import ujson as json
from fastapi import Form
from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    """Lifecycle states for a processing job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ServiceType(StrEnum):
    """Logical services that report status."""

    PDF = "pdf"
    AGENT = "agent"
    TTS = "tts"


class StatusSnapshot(BaseModel):
    """Status payload for a single service."""

    status: TaskStatus | None = None
    message: str | None = None
    progress: float | None = None


class ConversionStatus(StrEnum):
    """PDF conversion outcome."""

    SUCCESS = "success"
    FAILED = "failed"


class PdfConversionResult(BaseModel):
    """Result of a PDF conversion call."""

    filename: str
    content: str = ""
    status: ConversionStatus
    error: str | None = None


class PdfMetadata(BaseModel):
    """Processed PDF metadata."""

    filename: str
    markdown: str = ""
    summary: str = ""
    status: ConversionStatus
    type: Literal["target", "context"]
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DialogueEntry(BaseModel):
    """Single dialogue line."""

    text: str
    speaker: Literal["speaker-1", "speaker-2"]
    voice_id: str | None = None


class Conversation(BaseModel):
    """Conversation container."""

    scratchpad: str
    dialogue: list[DialogueEntry]


class GeneratePodcastRequest(BaseModel):
    """Payload for podcast generation."""

    user_id: str = Field(..., description="KAS user identifier")
    name: str = Field(..., description="Podcast name")
    duration: int = Field(..., description="Duration in minutes")
    monologue: bool = Field(default=False, description="True for single-speaker flow")
    speaker_1_name: str = Field(..., description="Name of the first speaker")
    speaker_2_name: str | None = Field(default=None, description="Name of the second speaker when not monologue")
    voice_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of speaker ids to voice ids; defaults provided when empty",
    )
    guide: str | None = Field(default=None, description="Optional focus instructions")
    task_id: str | None = Field(default=None, description="Optional externally provided task identifier")
    no_tts: bool = Field(default=False, description="Skip TTS audio generation, return transcript only")
    full_audio: bool = Field(default=False, description="Generate full audio; when false, use a short preview")

    @model_validator(mode="after")
    def validate_speakers(self) -> "GeneratePodcastRequest":
        """Validate monologue vs dialogue speaker requirements.

        Returns:
            GeneratePodcastRequest: Validated instance.

        Raises:
            ValueError: If speaker configuration is invalid.
        """
        if self.monologue:
            if self.speaker_2_name is not None:
                raise ValueError("speaker_2_name must be omitted for monologue flow")
        else:
            if not self.speaker_2_name:
                raise ValueError("speaker_2_name is required for dialogue flow")
        return self

    @classmethod
    def as_form(
        cls,
        user_id: Annotated[str, Form(...)],
        name: Annotated[str, Form(...)],
        duration: Annotated[int, Form(...)],
        speaker_1_name: Annotated[str, Form(...)],
        monologue: Annotated[bool, Form()] = False,
        speaker_2_name: Annotated[str | None, Form()] = None,
        guide: Annotated[str | None, Form()] = None,
        voice_mapping: Annotated[str | None, Form()] = None,
        task_id: Annotated[str | None, Form()] = None,
        no_tts: Annotated[bool, Form()] = False,
        full_audio: Annotated[bool, Form()] = False,
    ) -> "GeneratePodcastRequest":
        """Create instance from form-data (used by FastAPI Depends).

        Args:
            user_id (str): User identifier.
            name (str): Podcast name.
            duration (int): Duration in minutes.
            monologue (bool): True for single-speaker flow.
            speaker_1_name (str): Name of the first speaker.
            speaker_2_name (str | None): Name of the second speaker when not monologue.
            guide (str | None): Optional focus instructions.
            voice_mapping (str | None): JSON string mapping speaker ids to voice ids.
            task_id (str | None): Optional externally provided task identifier.
            no_tts (bool): Skip TTS audio generation.
            full_audio (bool): Generate full audio; when false, use a short preview

        Returns:
            GeneratePodcastRequest: Parsed request instance.
        """
        parsed_voice_mapping: dict[str, str] = {}

        if voice_mapping:

            try:
                parsed_voice_mapping = json.loads(voice_mapping)
            except Exception:
                parsed_voice_mapping = {}

        return cls(
            user_id=user_id,
            name=name,
            duration=duration,
            monologue=monologue,
            speaker_1_name=speaker_1_name,
            speaker_2_name=speaker_2_name,
            guide=guide,
            voice_mapping=parsed_voice_mapping,
            task_id=task_id,
            no_tts=no_tts,
            full_audio=full_audio,
        )


class StatusResponse(BaseModel):
    """Aggregated status response for API consumers."""

    task_id: str
    status: TaskStatus
    message: str
    services: dict[str, StatusSnapshot]


class SegmentPoint(BaseModel):
    """Model representing a key point within a podcast segment topic.

    Attributes:
        description (str): Description of the point to be covered.
    """

    description: str


class SegmentTopic(BaseModel):
    """Model representing a topic within a podcast segment.

    Attributes:
        title (str): Title of the topic.
        points (list[SegmentPoint]): List of key points to cover in the topic.
    """

    title: str
    points: list[SegmentPoint]


class PodcastSegment(BaseModel):
    """Model representing a segment of a podcast.

    Attributes:
        section (str): Name or title of the segment.
        topics (list[SegmentTopic]): List of topics to cover in the segment.
        duration (int): Duration of the segment in seconds.
        references (list[str]): List of reference sources for the segment content.
    """

    section: str
    topics: list[SegmentTopic]
    duration: int
    references: list[str]


class PodcastOutline(BaseModel):
    """Model representing the complete outline of a podcast.

    Attributes:
        title (str): Title of the podcast.
        segments (list[PodcastSegment]): List of segments making up the podcast.
    """

    title: str
    segments: list[PodcastSegment]
