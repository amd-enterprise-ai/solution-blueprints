# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
import logging
import time
import uuid
from datetime import datetime

import requests

from ..settings import (
    DEFAULT_DURATION,
    DEFAULT_PODCAST_NAME,
    DEFAULT_SPEAKER_1_NAME,
    DEFAULT_SPEAKER_2_NAME,
    DEFAULT_VOICE_SPEAKER_1,
    DEFAULT_VOICE_SPEAKER_2,
    MAX_RETRIES,
    MAX_WAIT_TIMEOUT,
    OUTPUT_DIR,
    RETRY_DELAY,
    TEST_USER_ID,
)
from .file_utils import create_empty_transcript, read_pdf_file, save_audio_file, save_transcript
from .status_monitor import StatusMonitor

log = logging.getLogger(__name__)


class PodcastService:
    """Service for managing podcast generation and API interactions."""

    def __init__(self, base_url: str, user_id: str = TEST_USER_ID):
        """
        Initialize the podcast service.

        Args:
            base_url: Base URL of the API service
            user_id: User ID for API requests (defaults to TEST_USER_ID)
        """
        self.base_url = base_url
        self.user_id = user_id

    def _get_output_with_retry(
        self, task_id: str, max_retries: int = MAX_RETRIES, retry_delay: int = RETRY_DELAY
    ) -> bytes:
        """Retry getting output with exponential backoff."""
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{self.base_url}/podcasts/{task_id}/audio", params={"user_id": self.user_id})
                if response.status_code == 200:
                    return response.content
                elif response.status_code == 404:
                    wait_time = retry_delay * (2**attempt)
                    log.info(
                        "[%s] Output not ready yet, retrying in %.1fs...",
                        datetime.now().strftime("%H:%M:%S"),
                        wait_time,
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    response.raise_for_status()
            except requests.RequestException as e:
                log.error("[%s] Error getting output: %s", datetime.now().strftime("%H:%M:%S"), e)
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay * (2**attempt))

        raise TimeoutError("Failed to get output after maximum retries")

    def _verify_saved_podcasts(self, task_id: str, max_retries: int = MAX_RETRIES, retry_delay: int = 5):
        """Validate saved podcasts endpoints with retry logic."""
        log.info("[%s] Verifying podcast endpoints...", datetime.now().strftime("%H:%M:%S"))

        # Step 1: Get task status
        log.info("Verifying task status endpoint...")
        for attempt in range(max_retries):
            response = requests.get(f"{self.base_url}/podcasts/{task_id}/status")
            if response.status_code == 200:
                status_data = response.json()
                log.info("Successfully retrieved task status: %s", status_data.get("status", "unknown"))
                break
            elif attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)
                log.info(
                    "Task status not available yet, retrying in %.1fs... (attempt %d/%d)",
                    wait_time,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(wait_time)
                continue
            else:
                log.warning("Could not retrieve task status after %d attempts", max_retries)

        # Step 2: Get podcast audio
        log.info("Verifying podcast audio endpoint...")
        response = requests.get(f"{self.base_url}/podcasts/{task_id}/audio", params={"user_id": self.user_id})
        if response.status_code == 200:
            audio_data = response.content
            log.info("Successfully retrieved audio data, size: %d bytes", len(audio_data))
        else:
            log.warning("Could not retrieve audio: %s", response.text)

    def _fetch_transcript(self, filename: str, task_id: str) -> str:
        """Fetch and persist transcript JSON for a task."""
        # Try to get transcript from API endpoint
        try:
            response = requests.get(f"{self.base_url}/podcasts/{task_id}/transcript", params={"user_id": self.user_id})
            if response.status_code == 200:
                transcript_data = response.json()
                return save_transcript(filename, transcript_data)
            elif response.status_code == 404:
                log.warning("Transcript not found for task %s", task_id)
        except Exception as e:
            log.warning("Error retrieving transcript: %s", e)

        # Create empty file if endpoint not available
        return create_empty_transcript(filename)

    def _fetch_token_count(self, task_id: str) -> int | None:
        """Fetch full podcast token count from backend API."""
        try:
            response = requests.get(f"{self.base_url}/podcasts/{task_id}/tokens", params={"user_id": self.user_id})
            if response.status_code != 200:
                return None
            return int(response.json().get("tokens"))
        except Exception as exc:
            log.warning("Error retrieving token count: %s", exc)
            return None

    def _submit_podcast_job(
        self,
        target_files: list[str],
        context_files: list[str],
        output_id: str,
        monologue: bool,
        no_tts: bool,
        full_audio: bool,
    ) -> str:
        """
        Submit a podcast generation job and wait for completion.

        Args:
            target_files: List of target PDF file paths
            context_files: List of context PDF file paths
            output_id: Unique identifier for the output file
            monologue: Whether to generate a monologue (single speaker)
            no_tts: Skip TTS audio generation, return transcript only
            full_audio: Generate full audio, otherwise use a short preview

        Returns:
            Task ID of the submitted job

        """
        voice_mapping = {
            "speaker-1": DEFAULT_VOICE_SPEAKER_1,
        }

        if not monologue:
            voice_mapping["speaker-2"] = DEFAULT_VOICE_SPEAKER_2

        process_url = f"{self.base_url}/podcasts/generate"

        # Prepare form data - send parameters directly as form fields
        form_data = {
            "user_id": self.user_id,
            "name": DEFAULT_PODCAST_NAME,
            "duration": DEFAULT_DURATION,
            "speaker_1_name": DEFAULT_SPEAKER_1_NAME,
            "monologue": monologue,
            "voice_mapping": json.dumps(voice_mapping),
            "guide": None,
            "no_tts": no_tts,
            "full_audio": full_audio,
        }

        if not monologue:
            form_data["speaker_2_name"] = DEFAULT_SPEAKER_2_NAME

        log.info("[%s] Submitting PDFs for processing...", datetime.now().strftime("%H:%M:%S"))
        log.info("Using voices: %s", voice_mapping)

        # Prepare multipart form data with files
        files_data = []

        # Process target file (only first one is used as target)
        target_file = target_files[0]
        basename, content = read_pdf_file(target_file)
        files_data.append(("target_file", (basename, content, "application/pdf")))

        # Process context files
        if context_files:
            for pdf_file in context_files:
                basename, content = read_pdf_file(pdf_file)
                files_data.append(("context_files", (basename, content, "application/pdf")))

        try:
            log.info("Process URL: %s", process_url)
            response = requests.post(process_url, files=files_data, data=form_data)

            assert (
                response.status_code == 202
            ), f"Expected status code 202, but got {response.status_code}. Response: {response.text}"
            task_data = response.json()
            assert "task_id" in task_data, "Response missing task_id"
            task_id = task_data["task_id"]
            log.info("[%s] Task ID received: %s", datetime.now().strftime("%H:%M:%S"), task_id)

            # Step 2: Start monitoring status via WebSocket
            with StatusMonitor(self.base_url, task_id) as monitor:
                # Wait for TTS completion or timeout
                if not monitor.tts_completed.wait(timeout=MAX_WAIT_TIMEOUT):
                    raise TimeoutError(f"Test timed out after {MAX_WAIT_TIMEOUT} seconds")
                if monitor.failed:
                    raise RuntimeError("Generation failed in one of the services (see logs).")

                # If we get here, TTS completed successfully (or was skipped)
                if no_tts:
                    log.info(
                        "[%s] TTS skipped (no_tts flag enabled), skipping audio retrieval",
                        datetime.now().strftime("%H:%M:%S"),
                    )

                else:
                    log.info(
                        "[%s] TTS processing completed, retrieving audio file...", datetime.now().strftime("%H:%M:%S")
                    )

                    # Get the final output with retry logic
                    audio_content = self._get_output_with_retry(task_id)

                    # Save the audio file
                    output_path = save_audio_file(output_id, audio_content)
                    log.info("[%s] Audio file saved as '%s'", datetime.now().strftime("%H:%M:%S"), output_path)

                    # Validate podcast endpoints with the newly created task_id
                    self._verify_saved_podcasts(task_id)

            return task_id

        except Exception as e:
            log.error("Error during PDF submission: %s", e)
            raise e

    def generate_podcast(
        self,
        target_files: list[str],
        context_files: list[str],
        settings: list[str],
    ) -> tuple[str | None, str, int | None]:
        """
        Generate podcast and return paths to audio and transcript.

        Args:
            target_files: List of target PDF file paths
            context_files: List of context PDF file paths
            settings: List of settings (e.g., ["Monologue Only", "No TTS"])

        Returns:
            Tuple of (audio_file_path or None, transcript_path, token_count)

        """
        monologue = "Monologue Only" in settings
        no_tts = "No TTS" in settings
        full_audio = "Full audio" in settings
        filename = str(uuid.uuid4())

        task_id = self._submit_podcast_job(
            target_files=target_files,
            context_files=context_files,
            output_id=filename,
            monologue=monologue,
            no_tts=no_tts,
            full_audio=full_audio,
        )

        # Only try to get audio file if no_tts is False
        audio_file_path = None

        if not no_tts:
            audio_file_path_obj = OUTPUT_DIR / f"{filename}-output.mp3"

            if audio_file_path_obj.exists():
                audio_file_path = audio_file_path_obj.absolute().as_posix()

        transcript_path = self._fetch_transcript(filename, task_id)
        token_count = self._fetch_token_count(task_id)

        return audio_file_path, transcript_path, token_count
