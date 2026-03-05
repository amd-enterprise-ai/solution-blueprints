# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Orchestrates PDF -> scenario -> TTS pipeline."""

import json
import logging
import uuid
from typing import Sequence

from core.models import Conversation, ConversionStatus, DialogueEntry, GeneratePodcastRequest, ServiceType, TaskStatus
from core.task_store import TaskStore
from domain.scenario_runner import ScenarioRunner
from domain.tts_runner import TtsRunner
from fastapi import BackgroundTasks, HTTPException, UploadFile
from infrastructure.pdf_converter import PdfConverter
from infrastructure.storage import LocalStorage
from settings import settings

logger = logging.getLogger(__name__)


class PodcastService:
    """High-level facade to run podcast generation."""

    PREVIEW_CHAR_LIMIT = 3000

    def __init__(
        self,
        *,
        task_store: TaskStore,
        storage: LocalStorage,
        pdf_converter: PdfConverter,
        scenario_runner: ScenarioRunner,
        tts_runner: TtsRunner,
    ) -> None:
        self._task_store = task_store
        self._storage = storage
        self._pdf_converter = pdf_converter
        self._scenario_runner = scenario_runner
        self._tts_runner = tts_runner

    async def start_task(
        self,
        *,
        request: GeneratePodcastRequest,
        files: Sequence[UploadFile],
        background_tasks: BackgroundTasks,
    ) -> str:
        """Create task, persist inputs, and enqueue background pipeline.

        Args:
            request (GeneratePodcastRequest): Podcast parameters.
            files (Sequence[UploadFile]): Uploaded PDF files (first is target, rest are context).
            background_tasks (BackgroundTasks): FastAPI background task manager.

        Returns:
            str: Task identifier.
        """
        task_id = request.task_id or str(uuid.uuid4())
        await self._task_store.create_task(task_id)
        background_tasks.add_task(self._run_pipeline, task_id, request, files)
        return task_id

    async def _run_pipeline(self, task_id: str, request: GeneratePodcastRequest, files: Sequence[UploadFile]) -> None:
        """Run the end-to-end pipeline for a task.

        Args:
            task_id (str): Task identifier.
            request (GeneratePodcastRequest): Request payload.
            files (Sequence[UploadFile]): Uploaded PDF files (first is target, rest are context).

        Returns:
            None
        """
        logger.info("Starting pipeline for task %s with %d file(s)", task_id, len(files))
        current_service: ServiceType | None = None
        try:
            if not files:
                raise HTTPException(status_code=400, detail="At least one file (target) is required")

            # Automatically assign types: first file is target, rest are context
            types = ["target"] + ["context"] * (len(files) - 1)
            logger.info("Task %s: File types assigned: %s", task_id, types)

            current_service = ServiceType.PDF
            logger.info("Task %s: Starting PDF conversion phase", task_id)
            await self._task_store.update_status(task_id, ServiceType.PDF, TaskStatus.PROCESSING, "Saving PDF files")
            pdf_bytes: list[bytes] = []
            filenames: list[str] = []
            for upload in files:
                content = await upload.read()
                pdf_bytes.append(content)
                filenames.append(upload.filename or "document.pdf")
                self._storage.store_file(
                    user_id=request.user_id,
                    task_id=task_id,
                    content=content,
                    filename=upload.filename or "document.pdf",
                    content_type=upload.content_type or "application/pdf",
                    metadata=request.model_dump(),
                )

            pdf_metadata = await self._pdf_converter.convert(
                task_id=task_id,
                user_id=request.user_id,
                filenames=filenames,
                types=types,
            )
            logger.info("Task %s: PDF conversion completed, %d file(s) converted", task_id, len(pdf_metadata))

            # Check if target file conversion failed
            target_metadata = next((m for m in pdf_metadata if m.type == "target"), None)

            if target_metadata and target_metadata.status == ConversionStatus.FAILED:
                error_msg = (
                    f"Target file conversion failed: {target_metadata.error or 'Unknown error'}. "
                    f"File: {target_metadata.filename}"
                )
                logger.error("Task %s: %s", task_id, error_msg)
                raise Exception("Target file conversion failed")

            voice_mapping = request.voice_mapping or settings.default_voice_mapping

            current_service = ServiceType.AGENT
            logger.info("Task %s: Starting scenario generation phase", task_id)
            conversation: Conversation = await self._scenario_runner.run(
                task_id=task_id,
                user_id=request.user_id,
                pdfs=pdf_metadata,
                monologue=request.monologue,
                guide=request.guide,
                speaker_1_name=request.speaker_1_name,
                speaker_2_name=request.speaker_2_name,
                duration=request.duration,
                voice_mapping=voice_mapping,
            )
            logger.info("Task %s: Scenario generation completed", task_id)
            self._store_conversation(
                user_id=request.user_id,
                task_id=task_id,
                conversation=conversation,
            )
            full_token_count = sum(len(entry.text) for entry in conversation.dialogue)
            conversation_for_tts = conversation

            if not request.full_audio:
                limited_dialogue = self._limit_dialogue(conversation.dialogue, self.PREVIEW_CHAR_LIMIT)
                conversation_for_tts = conversation.model_copy(update={"dialogue": limited_dialogue})

            current_service = ServiceType.TTS

            if request.no_tts:
                logger.info("Task %s: TTS synthesis skipped (no_tts flag enabled)", task_id)
                skip_message = "TTS skipped (no_tts flag enabled). " f"Full podcast tokens: {full_token_count}"
                await self._task_store.update_status(task_id, ServiceType.TTS, TaskStatus.COMPLETED, skip_message)
                logger.info("Task %s: Pipeline completed successfully (TTS skipped)", task_id)

            else:
                logger.info("Task %s: Starting TTS synthesis phase", task_id)
                audio = await self._tts_runner.synthesize(
                    task_id=task_id,
                    conversation=conversation_for_tts,
                    voice_mapping=voice_mapping,
                )
                self._storage.store_audio(
                    user_id=request.user_id,
                    task_id=task_id,
                    audio_content=audio,
                    filename=f"{task_id}.mp3",
                    metadata=request.model_dump(),
                )
                logger.info("Task %s: TTS synthesis completed, audio size: %d bytes", task_id, len(audio))
                # Mark all services as completed
                completed_message = f"Podcast generation completed. Full podcast tokens: {full_token_count}"
                await self._task_store.update_status(task_id, ServiceType.TTS, TaskStatus.COMPLETED, completed_message)
                logger.info("Task %s: Pipeline completed successfully", task_id)

        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "Pipeline failed for task %s at service %s: %s", task_id, current_service, error_msg, exc_info=True
            )

            # Update status for the failed service (or PDF if service not set yet)
            failed_service = current_service or ServiceType.PDF
            await self._task_store.update_status(task_id, failed_service, TaskStatus.FAILED, error_msg)

            # Don't re-raise - error is already logged and status updated
            # Background tasks should not raise exceptions as they are not handled by FastAPI

    @staticmethod
    def _limit_dialogue(dialogue: Sequence[DialogueEntry], max_chars: int) -> list[DialogueEntry]:
        """Return dialogue truncated to the first max_chars characters."""
        total = 0
        limited: list[DialogueEntry] = []

        for entry in dialogue:
            if total >= max_chars:
                break

            remaining = max_chars - total

            if len(entry.text) <= remaining:
                limited.append(entry)
                total += len(entry.text)
                continue

            if remaining > 0:
                limited.append(entry.model_copy(update={"text": entry.text[:remaining]}))
                total += remaining

            break

        return limited

    def _store_conversation(self, *, user_id: str, task_id: str, conversation: Conversation) -> None:
        dialogue_payload = {"dialogue": [entry.model_dump() for entry in conversation.dialogue]}
        self._storage.store_file(
            user_id=user_id,
            task_id=task_id,
            content=json.dumps(dialogue_payload, ensure_ascii=True).encode(),
            filename=f"{task_id}_conversation.json",
            content_type="application/json",
            metadata={"type": "conversation"},
        )

    async def get_token_count(self, *, task_id: str, user_id: str) -> int:
        """Compute full podcast token count from stored conversation."""
        conversation_file = self._storage.get_file(
            user_id=user_id,
            task_id=task_id,
            filename=f"{task_id}_conversation.json",
        )
        if not conversation_file:
            raise HTTPException(status_code=404, detail="Conversation not found")

        try:
            payload = json.loads(conversation_file.decode())
            dialogue = payload.get("dialogue", [])

        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to parse conversation") from exc

        return sum(len(entry.get("text", "")) for entry in dialogue)

    async def get_status(self, task_id: str) -> dict:
        """Return aggregated task status or raise 404.

        Args:
            task_id (str): Task identifier.

        Returns:
            dict: Aggregated status payload.
        """
        try:
            return await self._task_store.get_status(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Task not found")

    async def get_audio(self, *, task_id: str, user_id: str) -> bytes:
        """Fetch generated audio or raise 404.

        Args:
            task_id (str): Task identifier.
            user_id (str): User identifier.

        Returns:
            bytes: Audio payload.
        """
        audio = await self._task_store.get_audio(task_id)
        if audio:
            return audio
        file_audio = self._storage.get_file(user_id=user_id, task_id=task_id, filename=f"{task_id}.mp3")
        if file_audio:
            return file_audio
        raise HTTPException(status_code=404, detail="Audio not found")

    async def get_transcript(self, *, task_id: str, user_id: str) -> bytes:
        """Fetch transcript data or raise 404.

        Args:
            task_id (str): Task identifier.
            user_id (str): User identifier.

        Returns:
            bytes: Transcript JSON payload.
        """
        transcript = await self._task_store.get_transcript(task_id)

        if transcript:
            return transcript

        # Try to get from storage as fallback
        transcript_file = self._storage.get_file(
            user_id=user_id, task_id=task_id, filename=f"{task_id}_prompt_tracker.json"
        )

        if transcript_file:
            return transcript_file

        raise HTTPException(status_code=404, detail="Transcript not found")
