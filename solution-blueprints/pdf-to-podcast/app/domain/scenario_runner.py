# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Scenario generation runner reusing the existing agent builder."""


import json
import logging
from typing import Sequence

from agent.podcast_scenario_builder import PodcastScenarioBuilder
from agent.prompts import MONOLOGUE_PROMPTS, PODCAST_PROMPTS
from agent.utils import init_llm
from core.models import Conversation as ConversationModel
from core.models import PdfMetadata, ServiceType, TaskStatus
from core.task_store import TaskStore
from domain.prompt_tracker import PromptTracker
from infrastructure.storage import LocalStorage
from settings import settings

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Run the monologue/podcast scenario pipeline."""

    def __init__(self, task_store: TaskStore, storage: LocalStorage) -> None:
        """Initialize scenario runner.

        Args:
            task_store (TaskStore): Task state store.
            storage (LocalStorage): Local storage adapter.
        """
        self._task_store = task_store
        self._storage = storage

    async def run(
        self,
        *,
        task_id: str,
        user_id: str,
        pdfs: Sequence[PdfMetadata],
        monologue: bool,
        guide: str | None,
        speaker_1_name: str,
        speaker_2_name: str | None,
        duration: int,
        voice_mapping: dict[str, str],
    ) -> ConversationModel:
        """Generate a podcast conversation.

        Args:
            task_id (str): Task identifier.
            user_id (str): User identifier.
            pdfs (Sequence[PdfMetadata]): Converted PDF metadata.
            monologue (bool): Whether to run monologue flow.
            guide (str | None): Optional focus instructions.
            speaker_1_name (str): Name of first speaker.
            speaker_2_name (str | None): Name of second speaker.
            duration (int): Desired duration in minutes.
            voice_mapping (dict[str, str]): Voice mapping for speakers.

        Returns:
            ConversationModel: Generated conversation model.
        """
        logger.info("Task %s: Initializing scenario runner (monologue=%s)", task_id, monologue)
        await self._task_store.update_status(
            task_id, ServiceType.AGENT, TaskStatus.PROCESSING, "Starting scenario build"
        )

        # Initialize LLM (with retry logic and caching)
        logger.info("Task %s: Initializing LLM from %s", task_id, settings.llm_url)
        llm = await init_llm(settings.llm_url, settings.api_key)

        prompt_tracker = PromptTracker(task_id=task_id, user_id=user_id, storage=self._storage)

        prompt_templates = MONOLOGUE_PROMPTS if monologue else PODCAST_PROMPTS
        builder = PodcastScenarioBuilder(
            llm=llm,
            prompt_tracker=prompt_tracker,
            prompt_templates=prompt_templates,
            task_store=self._task_store,
        )

        request = _ScenarioRequest(
            pdf_metadata=list(pdfs),
            guide=guide,
            monologue=monologue,
            duration=duration,
            speaker_1_name=speaker_1_name,
            speaker_2_name=speaker_2_name,
            voice_mapping=voice_mapping,
        )
        conversation_raw = await builder.run(
            kind="monologue" if monologue else "podcast",
            pdfs=pdfs,
            request=request,  # type: ignore[arg-type]
            task_id=task_id,
        )
        conversation: ConversationModel = ConversationModel.model_validate(conversation_raw.model_dump())
        logger.info("Task %s: Scenario generated with %d dialogue entries", task_id, len(conversation.dialogue))

        await self._task_store.update_status(
            task_id, ServiceType.AGENT, TaskStatus.COMPLETED, "Scenario generation completed", progress=1.0
        )

        # Get prompt tracker data (steps) and combine with conversation
        transcript_data: dict[str, list[dict]] = {"steps": []}
        prompt_tracker_file = self._storage.get_file(
            user_id=user_id,
            task_id=task_id,
            filename=f"{task_id}_prompt_tracker.json",
        )
        if prompt_tracker_file:
            try:
                prompt_tracker_data = json.loads(prompt_tracker_file.decode())
                transcript_data["steps"] = prompt_tracker_data.get("steps", [])
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Task %s: Failed to parse prompt tracker data: %s", task_id, e)

        # Save transcript with steps
        transcript_json = json.dumps(transcript_data, indent=2)
        await self._task_store.set_transcript(task_id, transcript_json.encode())
        return conversation


class _ScenarioRequest:
    """Minimal request shim matching builder expectations."""

    def __init__(
        self,
        *,
        pdf_metadata: list[PdfMetadata],
        guide: str | None,
        monologue: bool,
        duration: int,
        speaker_1_name: str,
        speaker_2_name: str | None,
        voice_mapping: dict[str, str],
    ) -> None:
        self.pdf_metadata = pdf_metadata
        self.guide = guide
        self.monologue = monologue
        self.duration = duration
        self.speaker_1_name = speaker_1_name
        self.speaker_2_name = speaker_2_name
        self.voice_mapping = voice_mapping
