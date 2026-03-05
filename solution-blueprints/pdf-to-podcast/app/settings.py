# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Configuration objects for the service."""

from pathlib import Path
from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="APP_", case_sensitive=False, env_file=Path(__file__).parent / ".env")

    pwd: ClassVar = Path(__file__).parent

    storage_path: Path = Field(default=Path("/tmp/storage"), description="Local path for storing files and audio")
    model_api_timeout: int = Field(default=600, description="Timeout in seconds for PDF conversion requests")
    api_key: str = Field(default="test_key", description="API key for LLM")
    llm_url: str = Field(description="Base URL for LLM service (OpenAI-compatible API)")

    elevenlabs_api_key: str = Field(default="test_key", description="API key for ElevenLabs")
    celery_broker_url: str = Field(default="redis://localhost:6379/0", description="Celery broker URL (Redis)")
    celery_backend_url: str = Field(default="redis://localhost:6379/0", description="Celery result backend URL")

    tts_model: str = Field(default="eleven_multilingual_v2", description="TTS model identifier")
    tts_audio_format: str = Field(default="mp3_44100_128", description="Output audio format")
    tts_concurrent_limit: int = Field(default=1, description="Max concurrent TTS batch size")
    tts_voice_1_default: str = Field(default="Xb7hH8MSUJpSbSDYk0k2", description="Default voice for speaker-1")
    tts_voice_2_default: str = Field(default="IKne3meq5aSn9XLyUdCD", description="Default voice for speaker-2")
    tts_stability_level: float = Field(default=0.5, description="ElevenLabs stability parameter")
    tts_similarity_boost: float = Field(default=0.75, description="ElevenLabs similarity boost")
    tts_style_exaggeration: float = Field(default=0.0, description="ElevenLabs style exaggeration")

    @field_validator("storage_path", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path) -> Path:
        """Ensure storage path is absolute."""
        path = Path(value).expanduser()
        return path if path.is_absolute() else Path.cwd() / path

    @property
    def default_voice_mapping(self) -> dict[str, str]:
        """Return default mapping of speakers to voice ids."""
        return {
            "speaker-1": self.tts_voice_1_default,
            "speaker-2": self.tts_voice_2_default,
        }


settings = Settings()
