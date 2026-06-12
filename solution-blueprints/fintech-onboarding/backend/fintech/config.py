# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # InsightFace: buffalo_l or antelopev2
    insightface_model_name: str = os.getenv("INSIGHTFACE_MODEL_NAME", "antelopev2")

    det_size: tuple = (640, 640)
    ctx_id: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
