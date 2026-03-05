# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""TTS synthesis adapter without Redis/MinIO dependencies."""


import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from core.models import Conversation, DialogueEntry, ServiceType, TaskStatus
from core.task_store import TaskStore
from elevenlabs.client import ElevenLabs
from settings import settings

logger = logging.getLogger(__name__)


class TtsRunner:
    """Generate audio for a conversation."""

    def __init__(self, task_store: TaskStore) -> None:
        """Create TTS runner.

        Args:
            task_store (TaskStore): Task state store.
        """
        self._task_store = task_store
        self._executor = ThreadPoolExecutor(max_workers=settings.tts_concurrent_limit)
        self._client = ElevenLabs(api_key=settings.elevenlabs_api_key, timeout=120.0)

    async def synthesize(self, *, task_id: str, conversation: Conversation, voice_mapping: dict[str, str]) -> bytes:
        """Convert conversation dialogue to audio bytes.

        Args:
            task_id (str): Task identifier.
            conversation (Conversation): Conversation to synthesize.
            voice_mapping (dict[str, str]): Mapping of speakers to voice ids.

        Returns:
            bytes: Audio payload in configured format.
        """
        logger.info("Task %s: Starting TTS synthesis for %d dialogue entries", task_id, len(conversation.dialogue))
        await self._task_store.update_status(task_id, ServiceType.TTS, TaskStatus.PROCESSING, "Starting TTS")
        mapping = self._resolve_mapping(voice_mapping)
        batches = self._chunk(conversation.dialogue, settings.tts_concurrent_limit)
        logger.info("Task %s: Split into %d batch(es) for TTS processing", task_id, len(batches))

        audio_bytes = b""
        total_batches = len(batches)
        for idx, batch in enumerate(batches, start=1):
            await self._task_store.update_status(
                task_id,
                ServiceType.TTS,
                TaskStatus.PROCESSING,
                f"Processing batch {idx} of {total_batches}",
                progress=idx / total_batches,
            )
            batch_audio = await self._process_batch(batch, mapping)
            audio_bytes += batch_audio

        await self._task_store.update_status(
            task_id, ServiceType.TTS, TaskStatus.COMPLETED, "TTS completed", progress=1.0
        )
        await self._task_store.set_audio(task_id, audio_bytes)
        return audio_bytes

    def _resolve_mapping(self, requested: dict[str, str]) -> dict[str, str]:
        if requested:
            return requested
        return settings.default_voice_mapping

    async def _process_batch(self, batch: Iterable[DialogueEntry], mapping: dict[str, str]) -> bytes:
        """Process one batch of dialogue lines concurrently.

        Args:
            batch (Iterable[DialogueEntry]): Dialogue lines.
            mapping (dict[str, str]): Speaker to voice mapping.

        Returns:
            bytes: Concatenated audio for the batch.
        """
        loop = asyncio.get_running_loop()
        futures = []
        for line in batch:
            voice_id = line.voice_id or mapping.get(line.speaker, settings.tts_voice_1_default)
            futures.append(loop.run_in_executor(self._executor, self._synthesize_text, line.text, voice_id))
        results = await asyncio.gather(*futures)
        return b"".join(results)

    def _synthesize_text(self, text: str, voice_id: str) -> bytes:
        try:
            stream = self._client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=settings.tts_model,
                output_format=settings.tts_audio_format,
                voice_settings={
                    "stability": settings.tts_stability_level,
                    "similarity_boost": settings.tts_similarity_boost,
                    "style": settings.tts_style_exaggeration,
                },
            )
            return b"".join(stream)
        except Exception as exc:
            logger.error("TTS synthesis error: %s", exc)
            raise

    @staticmethod
    def _chunk(items: list[DialogueEntry], size: int) -> list[list[DialogueEntry]]:
        return [items[i : i + size] for i in range(0, len(items), size)]
