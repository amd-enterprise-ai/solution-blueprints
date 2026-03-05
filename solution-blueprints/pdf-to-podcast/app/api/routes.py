# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""API routes for the app service."""

import json
from typing import Annotated

from bootstrap import broadcaster, podcast_service
from core.models import GeneratePodcastRequest, StatusResponse
from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/podcasts", tags=["podcasts"])


@router.post("/generate", status_code=202)
async def generate_podcast(
    background_tasks: BackgroundTasks,
    payload: Annotated[GeneratePodcastRequest, Depends(GeneratePodcastRequest.as_form)],
    target_file: Annotated[UploadFile, File(description="Target PDF file")],
    context_files: Annotated[list[UploadFile] | None, File(description="Optional context PDF files")] = None,
) -> JSONResponse:
    """Trigger podcast generation.

    Args:
        background_tasks (BackgroundTasks): FastAPI background tasks manager.
        payload (GeneratePodcastRequest): Parsed request payload from form.
        target_file (UploadFile): Target PDF file (main document).
        context_files (list[UploadFile] | None): Optional context PDF files for additional information.

    Returns:
        JSONResponse: Task identifier.
    """
    # Combine target file with context files
    all_files = [target_file]
    if context_files:
        all_files.extend(context_files)

    task_id = await podcast_service.start_task(request=payload, files=all_files, background_tasks=background_tasks)
    return JSONResponse({"task_id": task_id}, status_code=202)


@router.get("/{task_id}/status", response_model=StatusResponse)
async def get_status(task_id: str) -> StatusResponse:
    """Return task status.

    Args:
        task_id (str): Task identifier.

    Returns:
        StatusResponse: Aggregated status payload.
    """
    status = await podcast_service.get_status(task_id)
    return StatusResponse(**status)


@router.get("/{task_id}/audio")
async def get_audio(task_id: str, user_id: Annotated[str, Query(...)]) -> StreamingResponse:
    """Download generated audio.

    Args:
        task_id (str): Task identifier.
        user_id (str): User identifier for lookup.

    Returns:
        StreamingResponse: MP3 stream.
    """
    audio = await podcast_service.get_audio(task_id=task_id, user_id=user_id)
    return StreamingResponse(iter([audio]), media_type="audio/mpeg")


@router.get("/{task_id}/transcript")
async def get_transcript(task_id: str, user_id: Annotated[str, Query(...)]) -> JSONResponse:
    """Get transcript with generation steps.

    Args:
        task_id (str): Task identifier.
        user_id (str): User identifier for lookup.

    Returns:
        JSONResponse: Transcript JSON with steps.
    """
    transcript = await podcast_service.get_transcript(task_id=task_id, user_id=user_id)
    return JSONResponse(json.loads(transcript.decode()))


@router.get("/{task_id}/tokens")
async def get_tokens(task_id: str, user_id: Annotated[str, Query(...)]) -> JSONResponse:
    """Get full podcast token count.

    Args:
        task_id (str): Task identifier.
        user_id (str): User identifier for lookup.

    Returns:
        JSONResponse: Token count payload.
    """
    tokens = await podcast_service.get_token_count(task_id=task_id, user_id=user_id)
    return JSONResponse({"tokens": tokens})


@router.websocket("/{task_id}/status")
async def websocket_status(task_id: str, websocket: WebSocket) -> None:
    """WebSocket endpoint for live status updates.

    Args:
        task_id (str): Task identifier.
        websocket (WebSocket): Client WebSocket.
    """
    await broadcaster.connect(websocket, task_id)
    try:
        while True:
            await websocket.receive_text()
    finally:
        await broadcaster.disconnect(websocket, task_id)
