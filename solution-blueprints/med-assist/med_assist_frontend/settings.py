# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import ClassVar

from pydantic import SecretStr, WebsocketUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(case_sensitive=False, env_file=Path(__file__).parent / ".env")

    pwd: ClassVar = Path(__file__).parent

    livekit_api_key: SecretStr = SecretStr("APIhSHdhCSBtLXU")
    livekit_api_secret: SecretStr = SecretStr("hueQUixySH0Yu6Vo6EYnLZYeIaQvhQfMLZTezKNNqgLA")
    livekit_room: str = "consultation"
    livekit_ws_url: WebsocketUrl

    client_html: Path = Path(__file__).parent / "index.html"


settings = Settings()
