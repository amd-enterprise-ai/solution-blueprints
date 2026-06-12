# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import ClassVar

from pydantic import HttpUrl, SecretStr, WebsocketUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(case_sensitive=False, env_file=Path(__file__).parent / ".env")

    pwd: ClassVar = Path(__file__).parent

    livekit_api_key: SecretStr = SecretStr("APIhSHdhCSBtLXU")
    livekit_api_secret: SecretStr = SecretStr("hueQUixySH0Yu6Vo6EYnLZYeIaQvhQfMLZTezKNNqgLA")
    livekit_ws_url: WebsocketUrl

    llm_api_key: SecretStr = SecretStr("test_key")
    llm_url: HttpUrl

    stt_model: str = "Qwen/Qwen3-ASR-1.7B"
    stt_base_url: HttpUrl
    stt_api_key: SecretStr = SecretStr("test_key")

    client_html: Path = Path(__file__).parent / "index.html"


settings = Settings()
