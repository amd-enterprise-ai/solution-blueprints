# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""PDF conversion adapter using Celery + Redis."""


import asyncio
import logging
from typing import Sequence

from celery.result import AsyncResult
from core.models import ConversionStatus, PdfConversionResult, PdfMetadata, ServiceType, TaskStatus
from core.task_store import TaskStore
from fastapi import HTTPException
from infrastructure.celery_client import get_celery_app
from infrastructure.storage import LocalStorage
from settings import settings

logger = logging.getLogger(__name__)


class PdfConverter:
    """Convert PDFs to markdown content via Celery task."""

    def __init__(self, task_store: TaskStore, storage: LocalStorage) -> None:
        self._task_store = task_store
        self._storage = storage
        self._timeout = settings.model_api_timeout
        self._celery = get_celery_app()

    async def convert(
        self,
        *,
        task_id: str,
        user_id: str,
        filenames: Sequence[str],
        types: Sequence[str],
    ) -> list[PdfMetadata]:
        """Convert PDFs and return metadata list.

        Args:
            task_id (str): Task identifier.
            user_id (str): User identifier.
            filenames (Sequence[str]): Original file names (files must already be stored).
            types (Sequence[str]): Document type per file ("target" or "context").

        Returns:
            list[PdfMetadata]: Conversion results.
        """
        logger.info("Task %s: Queuing %d PDF file(s) for conversion", task_id, len(filenames))
        await self._task_store.update_status(
            task_id, ServiceType.PDF, TaskStatus.PROCESSING, f"Queued {len(filenames)} PDFs", progress=0.05
        )

        # Build file paths - files are already stored in storage
        file_paths: list[str] = []
        for filename in filenames:
            file_path = self._storage._task_dir(user_id, task_id) / filename
            file_paths.append(str(file_path.absolute()))

        payload = [
            {
                "filename": filename,
                "file_path": file_path,
                "type": doc_type,
            }
            for filename, file_path, doc_type in zip(filenames, file_paths, types)
        ]

        celery_result = self._celery.send_task("pdf.convert", args=[task_id, payload, str(settings.storage_path)])
        logger.info("Task %s: Celery task sent, task_id: %s", task_id, celery_result.id)

        await self._task_store.update_status(
            task_id, ServiceType.PDF, TaskStatus.PROCESSING, "PDF conversion started", progress=0.1
        )

        results = await self._poll_celery(task_id, celery_result)
        logger.info("Task %s: Received %d conversion result(s)", task_id, len(results))

        await self._task_store.update_status(task_id, ServiceType.PDF, TaskStatus.PROCESSING, "Building metadata")

        metadata_list: list[PdfMetadata] = []
        for filename, result, doc_type in zip(filenames, results, types):
            metadata_list.append(
                PdfMetadata(
                    filename=filename,
                    markdown=result.content if result.status == ConversionStatus.SUCCESS else "",
                    status=result.status,
                    type=doc_type,
                    error=result.error,
                )
            )

        await self._task_store.update_status(
            task_id, ServiceType.PDF, TaskStatus.COMPLETED, "PDF conversion finished", progress=1.0
        )
        return metadata_list

    async def _poll_celery(self, task_id: str, celery_result: AsyncResult) -> list[PdfConversionResult]:
        """Poll Celery backend and translate results.

        Args:
            task_id (str): Task identifier.
            celery_result (AsyncResult): Celery async result handle.

        Returns:
            list[PdfConversionResult]: Converted results.

        Raises:
            HTTPException: On Celery failure, timeout, or missing results.
        """
        import time

        start_time = time.time()
        poll_count = 0

        try:
            while not celery_result.ready():
                elapsed = time.time() - start_time
                if elapsed > self._timeout:
                    raise HTTPException(
                        status_code=504,
                        detail=f"PDF conversion timeout after {self._timeout}s. "
                        "Ensure Celery worker is running and can process 'pdf.convert' tasks.",
                    )

                poll_count += 1
                if poll_count % 10 == 0:  # Update status every 10 seconds
                    await self._task_store.update_status(
                        task_id,
                        ServiceType.PDF,
                        TaskStatus.PROCESSING,
                        f"Waiting for PDF conversion ({int(elapsed)}s elapsed)",
                    )
                await asyncio.sleep(1)

            if celery_result.failed():
                error_detail = str(celery_result.result)
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF conversion failed: {error_detail}. " "Check Celery worker logs for details.",
                )

            raw_results = celery_result.result or []
            if not raw_results:
                raise HTTPException(
                    status_code=500,
                    detail="PDF conversion returned empty results. " "Ensure Celery worker is properly configured.",
                )

            return [
                PdfConversionResult(
                    filename=item.get("filename", f"doc_{idx}.pdf"),
                    content=item.get("content", ""),
                    status=ConversionStatus.SUCCESS if item.get("status") == "success" else ConversionStatus.FAILED,
                    error=item.get("error"),
                )
                for idx, item in enumerate(raw_results)
            ]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Celery polling failed: {exc}. "
                "Ensure Celery worker is running and Redis broker is accessible.",
            ) from exc
