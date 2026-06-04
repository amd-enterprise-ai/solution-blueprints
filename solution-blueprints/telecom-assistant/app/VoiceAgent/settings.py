# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    redis_url: str | None = Field(default=None, description="The redis url to connect to Redis")

    chroma_url: str | None = Field(default=None, description="The base url to use for ChromaDB")
    collection_name: str = Field(default="billing_docs", description="The ChromaDB collection name")

    embeddings_url: str | None = Field(default=None, description="The base url to use for embeddings")
    embeddings_api_key: str = Field(default="no-key-required", description="The key to use for embeddings")
    embeddings_model: str = Field(
        default="intfloat/multilingual-e5-large-instruct", description="The model used for embeddings"
    )

    bssgateway_url: str | None = Field(default=None, description="The base url to use for BSSGateway")

    libredesk_url: str | None = Field(default=None, description="The base url to use for LibreDesk")
    libredesk_token: str | None = Field(default=None, description="The token to use for LibreDesk")
    libredesk_inbox_id: int = Field(default=1, description="The id of the inbox in LibreDesk")

    stt_model: str = Field(default="Qwen/Qwen3-ASR-1.7B", description="The model used for STT")
    stt_base_url: str | None = Field(default=None, description="The base url to use for STT")
    stt_api_key: str = Field(default="no-key-required", description="The key to use for STT API")

    llm_model: str = Field(default="openai/gpt-oss-120b", description="The model used for LLM")
    llm_base_url: str | None = Field(default=None, description="The base url to use for LLM")
    llm_api_key: str = Field(default="no-key-required", description="The key to use for LLM API")

    tts_model: str = Field(default="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", description="The model used for TTS")
    tts_base_url: str | None = Field(default=None, description="The base url to use for TTS")
    tts_api_key: str = Field(default="no-key-required", description="The key to use for TTS")
    tts_voice: str = Field(default="Aiden", description="The voice to use for TTS")


settings = Settings()
