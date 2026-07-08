# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import base64
import io
import logging
from typing import Optional

import aiohttp
from openai import AsyncOpenAI
from settings import settings

logger = logging.getLogger(__name__)


class VLMClient:
    def __init__(self):
        raw_url = settings.vlm_base_url
        logger.info(f"Raw VLM_BASE_URL from settings: {repr(raw_url)}")
        self.base_url = raw_url.strip() if raw_url else None
        logger.info(f"VLM_BASE_URL: {repr(self.base_url)}")
        self.api_key = settings.vlm_api_key or "no-key-required"
        self.model_name = settings.vlm_model_name
        self._client: Optional[AsyncOpenAI] = None
        self._initialized = False

    async def initialize(self) -> str:
        """Initialize VLM client and discover model name if not set"""
        if self._initialized:
            return self.model_name

        if not self.base_url:
            raise ValueError("VLM_BASE_URL is not configured")

        logger.info(f"Using VLM URL: {self.base_url}")

        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=120.0,
        )

        # If model name is not configured, try to discover from /models endpoint
        if not self.model_name or self.model_name == "gpt-4o":
            await self._discover_model()

        self._initialized = True
        logger.info(f"VLMClient initialized with model: {self.model_name}")
        return self.model_name

    async def _discover_model(self, max_attempts: int = 120) -> None:
        """Discover available model from the /models endpoint"""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "no-key-required":
            headers["Authorization"] = f"Bearer {self.api_key}"

        base_url = self.base_url.rstrip("/")

        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{base_url}/models", headers=headers, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data") and len(data["data"]) > 0:
                                self.model_name = data["data"][0]["id"]
                                logger.info(f"Discovered VLM model: {self.model_name}")
                                return
                        logger.warning(f"Failed to get models from {base_url}/models, status: {resp.status}")
            except Exception as e:
                logger.warning(f"Model discovery attempt {attempt + 1} failed: {e}")

            await asyncio.sleep(1)

        raise RuntimeError(f"Failed to discover VLM model after {max_attempts} attempts")

    async def describe_image(
        self,
        image_bytes: bytes,
        filename: str,
        page_num: int,
        max_tokens: int = 700,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> str:
        """Describe an image using VLM with retries on failures"""
        if not self._initialized:
            await self.initialize()

        if self._client is None:
            logger.error("VLM client not initialized")
            return f"[Image description failed - client not initialized on page {page_num + 1}]"

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert at describing images for a RAG system. Describe all text, tables, charts and visual information accurately and in detail.",
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Describe this image from page {page_num + 1} of document '{filename}' in detail. Extract all visible text and important information.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                            ],
                        },
                    ],
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Attempt {attempt+1}/{max_retries} failed for {filename} page {page_num}: {e}")
                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    await asyncio.sleep(delay)

        return f"[Image description failed on page {page_num + 1} after {max_retries} attempts]"

    def _extract_frames_pyav(self, video_bytes: bytes, max_frames: int = 24) -> list[bytes]:
        """
        Extract frames from video bytes using PyAV.
        Dynamically adjusts number of frames based on duration.
        """
        try:
            import av
        except ImportError:
            logger.error("PyAV (av) is not installed. Cannot extract video frames.")
            return []

        frames_jpeg = []
        try:
            buf = io.BytesIO(video_bytes)
            container = av.open(buf)
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if video_stream is None:
                logger.error("No video stream found in uploaded file")
                container.close()
                return []

            # Get video duration
            duration_sec = 0.0
            if video_stream.duration is not None and video_stream.time_base:
                duration_sec = float(video_stream.duration * video_stream.time_base)
            elif container.duration and container.duration > 0:
                duration_sec = float(container.duration) / 1_000_000

            if duration_sec <= 0:
                num_frames = 8
            else:
                # ~1 frame every 2.2 seconds, min 6, max 24
                target = int(duration_sec / 2.2) + 1
                num_frames = max(6, min(max_frames, target))

            interval = duration_sec / num_frames if num_frames > 0 else 0
            logger.info(
                f"Video duration: {duration_sec:.1f}s, extracting {num_frames} frames "
                f"(~1 frame every {interval:.1f}s)"
            )

            # Get total frames
            total_frames = video_stream.frames
            if total_frames <= 0:
                logger.warning("Video stream.frames=0, counting via full decode pass")
                count = 0
                for _ in container.decode(video=0):
                    count += 1
                total_frames = count
                buf.seek(0)
                container.close()
                container = av.open(buf)

            if total_frames <= 0:
                logger.error("Video has 0 frames")
                container.close()
                return []

            # Select evenly spaced frames
            if num_frames >= total_frames:
                target_indices = set(range(total_frames))
            else:
                step = total_frames / num_frames
                target_indices = {int(i * step) for i in range(num_frames)}

            logger.info(f"Extracting at indices: {sorted(target_indices)}")

            current_idx = 0
            for frame in container.decode(video=0):
                if current_idx in target_indices:
                    pil_img = frame.to_image()
                    # Resize to keep payload reasonable
                    max_w = 1280
                    if pil_img.width > max_w:
                        ratio = max_w / pil_img.width
                        pil_img = pil_img.resize((max_w, int(pil_img.height * ratio)))
                    jpeg_buf = io.BytesIO()
                    pil_img.save(jpeg_buf, format="JPEG", quality=85)
                    frames_jpeg.append(jpeg_buf.getvalue())

                current_idx += 1
                if len(frames_jpeg) >= num_frames:
                    break

            container.close()

        except Exception as e:
            logger.error(f"PyAV frame extraction failed: {e}")

        logger.info(f"Extracted {len(frames_jpeg)} frames from video")
        return frames_jpeg

    async def describe_video(
        self,
        video_bytes: bytes,
        filename: str,
        max_retries: int = 2,
        retry_delay: float = 3.0,
    ) -> str:
        """
        Describe a video by extracting key frames via PyAV and sending them to the VLM.
        Uses adaptive max_tokens based on number of frames.
        """
        if not self._initialized:
            await self.initialize()

        if self._client is None:
            logger.error("VLM client not initialized")
            return "[Video description failed - VLM client not initialized]"

        # Extract frames
        frames_jpeg = await asyncio.get_event_loop().run_in_executor(
            None,
            self._extract_frames_pyav,
            video_bytes,
        )

        if not frames_jpeg:
            logger.error(f"No frames extracted from video {filename}")
            return "[Video description failed - could not extract frames from video]"

        num_frames = len(frames_jpeg)
        logger.info(f"Sending {num_frames} frames to VLM for {filename}")

        # Adaptive max_tokens depending on number of images
        if num_frames <= 8:
            effective_max_tokens = 950
        elif num_frames <= 12:
            effective_max_tokens = 750
        elif num_frames <= 18:
            effective_max_tokens = 600
        else:
            effective_max_tokens = 500

        logger.info(f"Using max_tokens={effective_max_tokens} for {num_frames} frames")

        # Build content
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"These are {num_frames} frames extracted from a video named '{filename}' "
                    "sent by a customer showing their router or optical network terminal (ONT). "
                    "Your task: identify the status of ALL LED indicator lights visible across these frames. "
                    "For each LED state: its label (e.g. Power, Broadband, Internet, LAN, LOS, PON, 2.4G, 5G), "
                    "its color (green, red, orange, white), and whether it is solid, flashing/blinking, or off. "
                    "If any LED changes state between frames (e.g. flashing pattern), describe it. "
                    "State the device model if any label is visible. "
                    "Give a clear structured summary of what you observe across all frames."
                ),
            }
        ]

        for frame_jpeg in frames_jpeg:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(frame_jpeg).decode('utf-8')}"},
                }
            )

        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    temperature=0.0,
                    max_tokens=effective_max_tokens,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert telecom field technician analyzing router and ONT "
                                "LED indicators from video frames. Be precise: "
                                "solid green = normal, flashing/blinking red = fault/loss of signal, "
                                "off = no connection on that interface. "
                                "Always highlight any red or flashing LEDs — these indicate faults."
                            ),
                        },
                        {
                            "role": "user",
                            "content": content,
                        },
                    ],
                )
                description = response.choices[0].message.content.strip()
                logger.info(f"VLM video description for {filename}: {description[:200]}...")
                return description
            except Exception as e:
                logger.error(f"VLM video attempt {attempt+1}/{max_retries} failed for {filename}: {e}")
                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)
                    logger.info(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        return f"[Video description failed for {filename} after {max_retries} attempts]"


# Global instance
_vlm_client: Optional[VLMClient] = None


async def get_vlm_client() -> VLMClient:
    """Get or create global VLM client instance"""
    global _vlm_client
    if _vlm_client is None:
        _vlm_client = VLMClient()
        await _vlm_client.initialize()
    return _vlm_client
