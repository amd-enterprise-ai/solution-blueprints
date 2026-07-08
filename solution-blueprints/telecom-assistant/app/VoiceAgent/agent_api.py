# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from ingest_chromadb import main as ingest_main
from livekit_agent_trigger_redis import notify_agent_new_file
from session_storage_redis import session_file_store
from vlm_client import get_vlm_client

logger = logging.getLogger(__name__)

# Maximum allowed upload size (bytes) to avoid exhausting pod memory on large
# or maliciously oversized uploads. Adjust per deployment requirements.
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
_READ_CHUNK_SIZE = 1024 * 1024  # 1MB


def _sanitize_for_log(value: object) -> str:
    return str(value).replace("\r", "").replace("\n", "")


async def _read_file_limited(file: UploadFile, max_size: int = MAX_UPLOAD_SIZE) -> bytes:
    """Read an UploadFile in chunks, enforcing a maximum size.

    Reading in fixed-size chunks (rather than a single `await file.read()`)
    means we never buffer more than `max_size` bytes regardless of what the
    client claims or sends, protecting against memory exhaustion from large
    or chunked-transfer uploads.
    """
    chunks = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise ValueError(f"File exceeds maximum allowed size of {max_size} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


app = FastAPI()


@app.post("/agent/ingest/pdf")
async def ingest_pdf(
    file: UploadFile = File(...),
    force: bool = Form(False),
    append: bool = Form(True),
):
    logger.info("FILE RECEIVED: %s", _sanitize_for_log(file.filename))

    try:
        data = await _read_file_limited(file)
    except ValueError as e:
        logger.warning(
            "Rejected upload due to size limit. filename=%s reason=%s",
            _sanitize_for_log(file.filename),
            _sanitize_for_log(e),
        )
        return JSONResponse(status_code=413, content={"error": "Uploaded file is too large."})

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(file.filename).name

        with open(path, "wb") as f:
            f.write(data)

        await ingest_main(
            pdf_path=str(path),
            force=force,
            append=append,
        )

    return {"status": "ok"}


@app.post("/agent/ingest/image")
async def ingest_image(
    file: UploadFile = File(...),
    room_name: str = Form(...),
):
    logger.info(
        "Image received for room: %s, file: %s",
        _sanitize_for_log(room_name),
        _sanitize_for_log(file.filename),
    )

    try:
        data = await _read_file_limited(file)
    except ValueError as e:
        logger.warning(
            "Rejected oversized image upload for room=%s file=%s: %s",
            _sanitize_for_log(room_name),
            _sanitize_for_log(file.filename),
            _sanitize_for_log(e),
        )
        return JSONResponse(status_code=413, content={"error": "Uploaded file is too large"})

    description = None
    if file.content_type and file.content_type.startswith("image/"):
        try:
            vlm = await get_vlm_client()
            description = await vlm.describe_image(data, file.filename, 0, max_retries=1)
            logger.info(f"VLM description generated: {description[:100]}...")
        except Exception as e:
            logger.error(f"VLM failed: {e}")

    file_id = await session_file_store.add_file(
        room_name=room_name,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        description=description,
    )

    await notify_agent_new_file(room_name, file_id, description)

    return {
        "status": "ok",
        "file_id": file_id,
        "room_name": room_name,
        "description": description,
    }


@app.post("/agent/ingest/video")
async def ingest_video(
    file: UploadFile = File(...),
    room_name: str = Form(...),
):
    logger.info(
        "Video received for room: %s, file: %s",
        _sanitize_for_log(room_name),
        _sanitize_for_log(file.filename),
    )

    try:
        data = await _read_file_limited(file)
    except ValueError as e:
        logger.warning(
            "Rejected video upload for room=%s file=%s due to invalid input or size limit: %s",
            _sanitize_for_log(room_name),
            _sanitize_for_log(file.filename),
            _sanitize_for_log(e),
        )
        return JSONResponse(
            status_code=413,
            content={"error": "Uploaded file is invalid or exceeds allowed size."},
        )

    # Attempt VLM video description by extracting frames
    description = None
    if file.content_type and file.content_type.startswith("video/"):
        try:
            vlm = await get_vlm_client()
            description = await vlm.describe_video(data, file.filename, max_retries=2)
            logger.info(f"VLM video description generated for {file.filename}: {description[:150]}...")
        except Exception as e:
            logger.error(f"VLM video description failed for {file.filename}: {e}")
            description = None
    else:
        logger.warning(
            f"Skipping VLM video description for {_sanitize_for_log(file.filename)}: "
            f"unexpected or missing content_type ({_sanitize_for_log(file.content_type)})"
        )

    file_id = await session_file_store.add_file(
        room_name=room_name,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        description=description,
    )
    await notify_agent_new_file(room_name, file_id, description)

    return {
        "status": "ok",
        "file_id": file_id,
        "room_name": room_name,
        "description": description or "Video received but frame extraction failed.",
    }


@app.post("/agent/session/rating")
async def save_session_rating(request: Request):
    """
    Called by the frontend after the user submits a rating in the modal.
    Saves the rating to Redis linked to the session summary.

    Expected JSON body:
    {
        "room_name": "voice_assistant_room_123",
        "rating": 4,
        "user_id": "abc123"   // optional
    }
    """
    try:
        body = await request.json()
        room_name = body.get("room_name")
        rating = body.get("rating")
        user_id = body.get("user_id")

        if not room_name:
            return JSONResponse(status_code=400, content={"error": "room_name is required"})
        if rating is None or not isinstance(rating, int) or not (1 <= rating <= 5):
            return JSONResponse(
                status_code=400,
                content={"error": "rating must be an integer between 1 and 5"},
            )

        record = await session_file_store.save_session_rating(room_name, rating, user_id)

        logger.info(
            "Rating saved: room=%s rating=%s user=%s",
            _sanitize_for_log(room_name),
            _sanitize_for_log(str(rating)),
            _sanitize_for_log(str(user_id)),
        )
        return JSONResponse(status_code=200, content={"status": "ok", "record": record})

    except Exception as e:
        logger.exception(f"Failed to save session rating: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to save rating"})


def run_ingest_server():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
    )
