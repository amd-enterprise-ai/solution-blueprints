# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Local filesystem storage."""


import json
from pathlib import Path

from settings import settings


class LocalStorage:
    """Manage task-scoped files on local disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.storage_path).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, user_id: str, task_id: str) -> Path:
        return self.root / user_id / task_id

    def store_file(
        self,
        *,
        user_id: str,
        task_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        metadata: dict | None = None,
    ) -> Path:
        """Persist a file and optional metadata sidecar.

        Args:
            user_id (str): User identifier.
            task_id (str): Task identifier.
            content (bytes): Raw bytes to store.
            filename (str): Target filename.
            content_type (str): MIME type for reference (stored in metadata sidecar).
            metadata (dict | None): Optional metadata to persist alongside.

        Returns:
            Path: Absolute path to stored file.
        """
        job_dir = self._task_dir(user_id, task_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        target = job_dir / filename
        target.write_bytes(content)

        meta_path = target.with_suffix(target.suffix + ".meta.json")
        meta_payload = {"content_type": content_type, "metadata": metadata or {}}
        meta_path.write_text(json.dumps(meta_payload))
        return target

    def store_audio(self, *, user_id: str, task_id: str, audio_content: bytes, filename: str, metadata: dict) -> Path:
        """Store audio with metadata.

        Args:
            user_id (str): User identifier.
            task_id (str): Task identifier.
            audio_content (bytes): MP3 payload.
            filename (str): Target filename.
            metadata (dict): Metadata to persist.

        Returns:
            Path: Absolute path to stored audio file.
        """
        return self.store_file(
            user_id=user_id,
            task_id=task_id,
            content=audio_content,
            filename=filename,
            content_type="audio/mpeg",
            metadata=metadata,
        )

    def get_file(self, *, user_id: str, task_id: str, filename: str) -> bytes | None:
        """Read a stored file if it exists.

        Args:
            user_id (str): User identifier.
            task_id (str): Task identifier.
            filename (str): Name of the file to read.

        Returns:
            bytes | None: File content or None.
        """
        target = self._task_dir(user_id, task_id) / filename
        return target.read_bytes() if target.exists() else None

    def list_audio_metadata(self, *, user_id: str) -> list[dict]:
        """List stored mp3 files for a user with metadata.

        Args:
            user_id (str): User identifier.

        Returns:
            list[dict]: Collection of audio metadata entries.
        """
        user_dir = self.root / user_id
        if not user_dir.exists():
            return []

        results: list[dict] = []
        for meta_path in user_dir.rglob("*.mp3.meta.json"):
            data = json.loads(meta_path.read_text())
            audio_path = meta_path.with_suffix("")  # strip .meta.json suffix
            stat = audio_path.stat()
            task_id = audio_path.parent.name
            results.append(
                {
                    "user_id": user_id,
                    "task_id": task_id,
                    "filename": audio_path.name,
                    "size": stat.st_size,
                    "created_at": stat.st_mtime,
                    "transcription_params": data.get("metadata", {}),
                }
            )
        results.sort(key=lambda item: item["created_at"], reverse=True)
        return results
