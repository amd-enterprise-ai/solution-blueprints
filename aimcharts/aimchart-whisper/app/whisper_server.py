# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
FastAPI ASR Transcription Service with Whisper backend.
"""

import base64  # Audio data encoding
import os  # File system operations
import uuid  # Temporary file naming
from typing import List, Optional

# HTTP Framework
import uvicorn  # ASGI server runner
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # Web framework
from fastapi.responses import Response  # HTTP responses

# Audio processing
from pydub import AudioSegment
from starlette.middleware.cors import CORSMiddleware

# Local modules
from whisper_comps.logger import CustomLogger
from whisper_comps.models import SpeechRecognitionResult
from whisper_model import AudioTranscriber


def enable_cross_origin(app_instance: FastAPI):
    app_instance.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=r"\w+",
        allow_methods=["OPTIONS", "POST", "GET"],
        allow_headers=["Authorization", "Content-Type", "*"],
    )


# ------------------------------------------------------------------
# Application setup
# ------------------------------------------------------------------

log = CustomLogger("asr-service")
app = FastAPI(title="Whisper ASR Service")

enable_cross_origin(app)

_engine: Optional[AudioTranscriber] = None


def _ensure_engine() -> AudioTranscriber:
    if _engine is None:
        log.error("ASR engine is not ready")
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _engine


def _write_temp_wav(data: bytes) -> str:
    filename = f"{uuid.uuid4().hex}.wav"
    with open(filename, "wb") as f:
        f.write(data)
    return filename


def _cleanup_file(path: Optional[str] = None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@app.get("/health")
async def service_status() -> Response:
    try:
        _ensure_engine()
        return Response(status_code=200, content="OK")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="ASR engine unavailable")


@app.post("/v1/asr")
async def transcribe_from_json(request: Request):
    log.info("Incoming JSON transcription request")

    engine = _ensure_engine()
    temp_file = None

    try:
        payload = await request.json()
        audio_blob = payload.get("audio")

        if not audio_blob:
            raise HTTPException(status_code=400, detail="Missing audio field")

        binary_audio = base64.b64decode(audio_blob)
        temp_file = _write_temp_wav(binary_audio)

        text = engine.transcribe(temp_file)
        log.info(f"JSON transcription completed ({len(text)} chars)")

        return {"transcription": text}

    except Exception:
        log.exception("JSON transcription failed")
        return {"transcription": "error", "error": "Internal server error"}

    finally:
        _cleanup_file(temp_file)


@app.post("/v1/audio/transcriptions")
async def transcribe_from_upload(
    audio_file: UploadFile = File(...),
    pretrained_model: str = Form("openai/whisper-small"),
    result_format: str = Form("json"),
    language_code: str = Form("english"),
    sampling_temp: float = Form(0),
    time_precision: Optional[List[str]] = Form(None),
    context_prompt: Optional[str] = Form(None),
):
    log.info("Incoming file-based transcription request")

    engine = _ensure_engine()

    if pretrained_model != os.getenv("ASR_MODEL_PATH", pretrained_model):
        log.warn(f"Requested model differs from loaded one: {pretrained_model}")

    engine.lang_code = language_code

    if any([context_prompt, result_format != "json", sampling_temp != 0, time_precision]):
        log.warn("Some advanced options are currently ignored")

    temp_file = None

    try:
        raw_bytes = await audio_file.read()
        temp_file = _write_temp_wav(raw_bytes)

        normalized = AudioSegment.from_file(temp_file).set_frame_rate(16000).set_channels(1)
        normalized.export(temp_file, format="wav")

        text = engine.transcribe(temp_file)
        log.info(f"Upload transcription completed ({len(text)} chars)")

        return SpeechRecognitionResult(text=text)

    except Exception:
        log.exception("Upload transcription failed")
        return SpeechRecognitionResult(text="processing error")

    finally:
        _cleanup_file(temp_file)


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------


@app.on_event("startup")
async def on_startup():
    global _engine

    log.info("Starting ASR engine initialization")

    _engine = AudioTranscriber(
        pretrained_model=os.getenv("ASR_MODEL_PATH", "openai/whisper-small"),
        language_code=os.getenv("TARGET_LANG", "english"),
        target_device=os.getenv("DEVICE", "cpu"),
        timestamp_support=os.getenv("WITH_TIMESTAMPS", "false").lower() == "true",
    )

    log.info(
        "Service ready | "
        f"model={os.getenv('ASR_MODEL_PATH', 'openai/whisper-small')} "
        f"device={os.getenv('DEVICE', 'cpu')} "
        f"port={os.getenv('PORT', '7066')}"
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7066")))
