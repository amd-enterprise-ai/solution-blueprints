# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import base64  # Encoding binary data to printable text
import os  # Operating system interface
from io import BytesIO as BinaryStream  # In-memory binary streams
from typing import Any, Dict, Iterable, List, Tuple, Union

import requests
from PIL import Image

Message = Dict[str, Any]
MessageInput = Union[str, Iterable[Message]]
EncodedImage = str


def _encode_image_to_base64(image: Image.Image) -> EncodedImage:
    """Serialize image as PNG and return a base64-encoded string."""
    buffer = BinaryStream()
    image.convert("RGBA").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _load_image_reference(ref: str) -> EncodedImage:
    """Load image from URL, local path or treat input as already base64-encoded."""
    if ref.startswith(("http://", "https://")):
        response = requests.get(ref)
        response.raise_for_status()
        img = Image.open(BinaryStream(response.content))
        return _encode_image_to_base64(img)

    if os.path.exists(ref):
        img = Image.open(ref)
        return _encode_image_to_base64(img)

    # Assume it is already a base64-encoded string or opaque token
    return ref


def _normalize_multimodal_user_content(raw_content: Any) -> Tuple[str, List[EncodedImage]]:
    """Extract text and image references from a multimodal user message."""
    text_chunks: List[str] = []
    image_refs: List[str] = []

    for item in raw_content:
        item_type = item.get("type")
        if item_type == "text":
            text_chunks.append(item.get("text", ""))
        elif item_type == "image_url":
            url = item.get("image_url", {}).get("url")
            if url:
                image_refs.append(url)
        # silently ignore unknown types to make parsing more robust

    text = "\n".join(chunk for chunk in text_chunks if chunk)
    encoded_images = [_load_image_reference(ref) for ref in image_refs]

    return text, encoded_images


def _build_prompt_from_messages(
    messages: Iterable[Message],
) -> Tuple[str, List[EncodedImage]]:
    """Build a plain-text prompt and collect base64 images from chat-style messages."""
    system_prefix = ""
    conversation_lines: List[str] = []
    collected_images: List[EncodedImage] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "system":
            system_prefix = str(content or "")
            continue

        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported role: {role}")

        line_prefix = f"{role}:"

        # multimodal user content (list of parts)
        if role == "user" and isinstance(content, list):
            text, images = _normalize_multimodal_user_content(content)
            if text:
                conversation_lines.append(f"{line_prefix} {text}")
            else:
                conversation_lines.append(line_prefix)
            collected_images.extend(images)
            continue

        # plain text message
        text_value = "" if content is None else str(content)
        if text_value:
            conversation_lines.append(f"{line_prefix} {text_value}")
        else:
            conversation_lines.append(line_prefix)

    prompt_parts: List[str] = []
    if system_prefix:
        prompt_parts.append(system_prefix)
    prompt_parts.extend(conversation_lines)

    prompt = "\n".join(prompt_parts)
    return prompt, collected_images


def render_prompt(messages: MessageInput) -> Union[str, Tuple[str, List[EncodedImage]]]:
    """Render input (string or chat-style messages) into a prompt and optional images."""
    if isinstance(messages, str):
        return messages

    prompt, images = _build_prompt_from_messages(messages)
    if images:
        return prompt, images
    return prompt
