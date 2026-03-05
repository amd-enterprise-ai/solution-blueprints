# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""In-memory task tracking with optional WebSocket notifications."""


import asyncio
import logging
import time
from dataclasses import dataclass, field

from core.models import ServiceType, StatusSnapshot, TaskStatus
from core.status_broadcaster import StatusBroadcaster

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """Internal container for task lifecycle data."""

    task_id: str
    created_at: float = field(default_factory=time.time)
    services: dict[ServiceType, StatusSnapshot] = field(
        default_factory=lambda: {service: StatusSnapshot() for service in ServiceType}
    )
    audio: bytes | None = None
    transcript: bytes | None = None
    final_status: TaskStatus = TaskStatus.PENDING
    message: str = "Task created"


class TaskStore:
    """Thread-safe task store with async notification hooks."""

    def __init__(self, broadcaster: StatusBroadcaster | None = None) -> None:
        self._records: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()
        self._broadcaster = broadcaster

    @property
    def records(self) -> dict[str, TaskRecord]:
        return self._records

    async def create_task(self, task_id: str) -> None:
        """Create a new task record.

        Args:
            task_id (str): Unique task identifier.
        """
        async with self._lock:
            self._records[task_id] = TaskRecord(task_id=task_id)
        await self._notify(task_id, None)

    async def update_status(
        self,
        task_id: str,
        service: ServiceType,
        status: TaskStatus,
        message: str = "",
        progress: float | None = None,
    ) -> None:
        """Update status for a specific service and broadcast.

        Args:
            task_id (str): Task identifier.
            service (ServiceType): Service being updated.
            status (TaskStatus): New status value.
            message (str): Human-readable message.
            progress (float | None): Optional progress [0..1].
        """
        async with self._lock:
            record = self._require(task_id)
            record.services[service] = StatusSnapshot(status=status, message=message, progress=progress)
            record.final_status = self._aggregate_status(record)
            record.message = message or record.message

        await self._notify(task_id, service)

    async def set_audio(self, task_id: str, audio: bytes) -> None:
        """Store synthesized audio.

        Args:
            task_id (str): Task identifier.
            audio (bytes): Audio payload.
        """
        async with self._lock:
            record = self._require(task_id)
            record.audio = audio

    async def set_transcript(self, task_id: str, transcript: bytes) -> None:
        """Store transcript data.

        Args:
            task_id (str): Task identifier.
            transcript (bytes): Serialized transcript JSON.
        """
        async with self._lock:
            record = self._require(task_id)
            record.transcript = transcript

    async def get_audio(self, task_id: str) -> bytes | None:
        """Return stored audio bytes if available.

        Args:
            task_id (str): Task identifier.

        Returns:
            bytes | None: Audio payload or None if missing.
        """
        async with self._lock:
            record = self._records.get(task_id)
            return record.audio if record else None

    async def get_transcript(self, task_id: str) -> bytes | None:
        """Return stored transcript bytes if available.

        Args:
            task_id (str): Task identifier.

        Returns:
            bytes | None: Transcript payload or None if missing.
        """
        async with self._lock:
            record = self._records.get(task_id)
            return record.transcript if record else None

    async def get_status(self, task_id: str) -> dict:
        """Return aggregated status for all services.

        Args:
            task_id (str): Task identifier.

        Returns:
            dict: Aggregated status payload.
        """
        async with self._lock:
            record = self._require(task_id)
            return {
                "task_id": task_id,
                "status": record.final_status,
                "message": record.message,
                "services": {svc.value: snap.model_dump() for svc, snap in record.services.items()},
            }

    def _require(self, task_id: str) -> TaskRecord:
        if task_id not in self._records:
            raise KeyError(f"Task {task_id} not found")
        return self._records[task_id]

    async def _notify(self, task_id: str, service: ServiceType | None) -> None:
        """Notify broadcaster about status change.

        Args:
            task_id (str): Task identifier.
            service (ServiceType | None): Service that changed, or None for initial creation.

        Returns:
            None
        """
        if not self._broadcaster:
            return
        try:
            payload = await self.get_status(task_id)
            payload["service"] = service.value if service else None
            await self._broadcaster.publish(task_id, payload)
            logger.debug("Status update sent for task %s, service %s: %s", task_id, service, payload.get("status"))
        except KeyError as exc:
            logger.warning("Failed to notify status for task %s: task not found", task_id)
        except Exception as exc:
            logger.error("Failed to notify status for task %s: %s", task_id, exc, exc_info=True)

    @staticmethod
    def _aggregate_status(record: TaskRecord) -> TaskStatus:
        statuses = {snap.status for snap in record.services.values() if snap.status is not None}
        if not statuses or statuses == {TaskStatus.PENDING}:
            return TaskStatus.PENDING
        if TaskStatus.FAILED in statuses:
            return TaskStatus.FAILED
        if statuses.issuperset({TaskStatus.COMPLETED}) and len(statuses) == 1:
            return TaskStatus.COMPLETED
        return TaskStatus.PROCESSING
