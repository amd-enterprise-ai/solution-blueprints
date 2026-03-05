# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import base64 as b64_enc  # Encoding utils
import binascii as bin_utils  # Binary tools
import os as _os  # OS interface
import subprocess as sub_proc  # Shell commands
import sys as _sys  # System params
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, List, Tuple, Union

import aiofiles  # type: ignore[import-untyped]
import httpx
import requests
from components import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    ChoiceFinishReason,
    DocumentSummarizer,
    ServiceRunner,
    TokenUsage,
    render_prompt,
)
from fastapi import File as MultipartFile
from fastapi import HTTPException as APIException
from fastapi import Request as ClientRequest
from fastapi import UploadFile as DataFile
from fastapi.responses import StreamingResponse as TokenStream

# Configuration
ASR_HOST = _os.getenv("ASR_SERVICE_HOST_IP", "0.0.0.0")
ASR_PORT = int(_os.getenv("ASR_SERVICE_PORT", "7066"))
LLM_BASE_URL = _os.getenv("LLM_ENDPOINT", "http://localhost:8000")
OPENAI_API_KEY = _os.getenv("OPENAI_API_KEY", None)
DOC_SUMMARY_ENDPOINT = "/v1/summarize"
SERVICE_PORT = 8888

SUPPORTED_DOC_TYPES = {"text", "document"}


class DocumentProcessor:
    """Unified document processing utilities."""

    MIME_HANDLERS = {
        "text/plain": "process_text",
        "application/pdf": "process_pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "process_docx",
        "application/octet-stream": "process_docx",
    }

    @staticmethod
    def process_pdf(path: Path) -> List[str]:
        from langchain_classic.document_loaders import PyPDFLoader

        return [doc.page_content for doc in PyPDFLoader(str(path)).load_and_split()]

    @staticmethod
    def process_text(path: Path) -> List[str]:
        from langchain_classic.text_splitter import CharacterTextSplitter

        return CharacterTextSplitter().split_text(path.read_text(encoding="utf-8"))

    @staticmethod
    def process_docx(path: Path) -> str:
        import docx2txt

        return docx2txt.process(str(path))

    def extract_content(self, path: Path, mime_type: str) -> Union[List[str], str]:
        """Extract document content based on MIME type."""
        handler_name = self.MIME_HANDLERS.get(mime_type)
        if not handler_name:
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        return getattr(self, handler_name)(path)


class MediaHandler:
    """Audio/Video processing utilities."""

    @staticmethod
    def to_base64(path: Path) -> str:
        """Convert file to base64."""
        return b64_enc.b64encode(path.read_bytes()).decode("utf-8")

    @staticmethod
    def extract_audio(video_b64: str) -> str | None:
        """Extract audio from base64 video using ffmpeg."""
        try:
            video_bytes = b64_enc.b64decode(video_b64, validate=True)
        except (bin_utils.Error, ValueError) as e:
            raise ValueError(f"Invalid base64 video: {e}") from e

        uid = uuid.uuid4().hex
        temp_dir = Path(tempfile.gettempdir())
        video_file = temp_dir / f"{uid}.mp4"
        audio_file = temp_dir / f"{uid}.wav"

        try:
            video_file.write_bytes(video_bytes)
            sub_proc.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(video_file),
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(audio_file),
                ],
                check=True,
                capture_output=True,
            )

            return MediaHandler.to_base64(audio_file)
        except sub_proc.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg failed: {e.stderr.decode()}") from e
        finally:
            video_file.unlink(missing_ok=True)
            audio_file.unlink(missing_ok=True)


def detect_model(
    endpoint: str,
    max_wait_seconds: int = 1200,
    retry_interval: int = 2,
) -> str:
    url = urllib.parse.urljoin(endpoint, "v1/models")
    start = time.time()

    while True:
        try:
            resp = requests.get(url, timeout=1.0)
            resp.raise_for_status()
            model = resp.json()["data"][0]["id"]
            print(f"Detected model: {model}", file=_sys.stderr)
            return model
        except (requests.RequestException, KeyError, IndexError):
            if time.time() - start > max_wait_seconds:
                raise RuntimeError(f"Model detection timed out after {max_wait_seconds} seconds")
            time.sleep(retry_interval)


class DocSumService:
    """Document summarization service with multi-modal support."""

    def __init__(self, service_host: str = "0.0.0.0", service_port: int = 8000):
        self.service = None
        self.service_host = service_host
        self.service_port = service_port
        self.endpoint = str(DOC_SUMMARY_ENDPOINT)
        self.doc_processor = DocumentProcessor()
        self.media_handler = MediaHandler()
        self.asr_url = f"http://{ASR_HOST}:{ASR_PORT}/v1/asr"

        # Initialize summarizer
        model_name = detect_model(LLM_BASE_URL)
        tokenizer = self._load_tokenizer(model_name)
        self.summarizer = DocumentSummarizer(llm_endpoint=LLM_BASE_URL, model_name=model_name, tokenizer=tokenizer)

    @staticmethod
    def _load_tokenizer(model_name: str):
        """Load tokenizer if available."""
        try:
            from transformers import AutoTokenizer

            return AutoTokenizer.from_pretrained(model_name)
        except Exception as e:
            print(f"Tokenizer unavailable: {e}", file=_sys.stderr)
            return None

    async def _transcribe_audio(self, audio_b64: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    self.asr_url, json={"audio": audio_b64}, headers={"Content-Type": "application/json"}
                )
                resp.raise_for_status()
                result = resp.json()
                transcription = result.get("asr_result") or result.get("text", "") or result.get("transcription", "")
                print(f"✅ ASR success: {len(transcription)} chars", file=_sys.stderr)
                return transcription
        except httpx.HTTPStatusError as e:
            print(f"ASR HTTP error {e.response.status_code}: {e.response.text[:200]}", file=_sys.stderr)
            return "ASR returned error - check audio format."
        except httpx.ConnectError:
            print(f"ASR connection failed: {self.asr_url}", file=_sys.stderr)
            return "ASR service temporarily unavailable."
        except Exception as e:
            print(f"ASR unexpected error: {e}", file=_sys.stderr)
            return f"ASR processing failed: {e}"

    async def _process_files(self, files: List[DataFile], data_type: str) -> list[Any] | None:
        if data_type not in {"text", "document", "audio", "video"}:
            raise ValueError(f"Unknown data type: {data_type}. Supported: text, document, audio, video")

        contents = []
        temp_dir = Path(tempfile.gettempdir())

        for file in files:
            file_path = temp_dir / f"{uuid.uuid4().hex}_{file.filename}"
            try:
                async with aiofiles.open(file_path, "wb") as f_out:
                    chunk_size = 64 * 1024
                    while True:
                        chunk = await file.read(chunk_size)
                        if not chunk:
                            break
                        await f_out.write(chunk)

                if data_type in SUPPORTED_DOC_TYPES:
                    extracted = self.doc_processor.extract_content(file_path, file.content_type)
                    contents.extend(extracted if isinstance(extracted, list) else [extracted])
                elif data_type == "audio":
                    contents.append(self.media_handler.to_base64(file_path))
                elif data_type == "video":
                    contents.append(self.media_handler.to_base64(file_path))

            finally:
                file_path.unlink(missing_ok=True)

        return contents

    async def handle_request(self, request: ClientRequest, files: List[DataFile] = MultipartFile(default=None)):
        """Handle summarization requests (JSON or multipart)."""
        content_type = request.headers.get("content-type", "")

        text_prompt: Union[str, Tuple[str, List[str]]] = ""
        document_text: str = ""
        media_payloads: list[str] = []

        if "application/json" in content_type:
            data = await request.json()
            chat_req = ChatRequest.model_validate(data)
            text_prompt = render_prompt(chat_req.conversation)
            data_type = data.get("type", "text")

        elif "multipart/form-data" in content_type:
            data = await request.form()
            chat_req = ChatRequest.model_validate(data)
            data_type = data.get("type", "text")

            text_prompt = render_prompt(chat_req.conversation)

            if files:
                async_result = await self._process_files(files, data_type)
                if async_result is not None:
                    if data_type in ("text", "document"):
                        document_text = "\n\n".join(async_result)
                    else:
                        media_payloads = [str(item) for item in async_result]

        else:
            raise APIException(400, f"Unsupported content type: {content_type}")

        summary_type = data.get("summary_type", "auto")
        max_tokens = chat_req.limit or 1024
        top_p = chat_req.prob_top_p or 0.95
        temperature = chat_req.temp or 0.01
        language = chat_req.lang_code or "auto"

        if data_type == "video":
            if not media_payloads:
                raise APIException(400, "Video file is required")

            audio_b64 = self.media_handler.extract_audio(media_payloads[0])
            if audio_b64:
                prompt = await self._transcribe_audio(audio_b64)
            else:
                prompt = ""

        elif data_type == "audio":
            if not media_payloads:
                raise APIException(400, "Audio file is required")

            prompt = await self._transcribe_audio(media_payloads[0])

        else:
            user_prompt = text_prompt[0] if isinstance(text_prompt, tuple) else text_prompt

            if document_text:
                prompt = f"{user_prompt}\n\n{document_text}"
            else:
                prompt = user_prompt

        result = await self.summarizer.summarize(
            text=prompt,
            summary_type=summary_type,
            language=language,
            max_tokens=max_tokens,
            top_p=top_p,
            temperature=temperature,
            access_token=OPENAI_API_KEY,
        )

        if isinstance(result, TokenStream):
            return result

        return ChatResponse(
            model="docsum",
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(role="assistant", content=result),
                    finish_reason=ChoiceFinishReason.STOP,
                )
            ],
            usage=TokenUsage(),
        )

    def start(self):
        """Start the service."""
        self.service = ServiceRunner(
            name=self.__class__.__name__,
            endpoint=self.endpoint,
            host=self.service_host,
            port=self.service_port,
            request_schema=ChatRequest,
            response_schema=ChatResponse,
        )
        # Configure API routes
        allowed_methods = ["POST"]
        self.service.add_route(path=self.endpoint, handler=self.handle_request, methods=allowed_methods)

        # Launch the microservice
        self.service.start()


# Entry point check
if __name__ == "__main__":
    DocSumService(service_port=SERVICE_PORT).start()
