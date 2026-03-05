# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Final

from gradio.utils import get_upload_folder

# Directory paths
# Use writable tmp paths to avoid read-only mounts
LOG_FILE_PATH: Final[Path] = Path("/tmp/frontend_output.log")
UPLOAD_DIR: Final[Path] = Path("/tmp/frontend_uploads")
OUTPUT_DIR: Final[Path] = Path("/tmp/frontend_outputs")
PWD: Final[Path] = Path(__file__).parent.parent

# Common variables
TEST_USER_ID: Final[str] = "test-userid"

# Retry settings
MAX_RETRIES: Final[int] = 5
RETRY_DELAY: Final[int] = 1
MAX_WAIT_TIMEOUT: Final[int] = 40 * 60  # 40 minutes in seconds

# WebSocket settings
WS_RECONNECT_DELAY: Final[float] = 1.0
WS_MAX_RECONNECT_DELAY: Final[float] = 30.0
WS_TIMEOUT: Final[int] = 30

# Voice mapping
DEFAULT_VOICE_SPEAKER_1: Final[str] = "Xb7hH8MSUJpSbSDYk0k2"
DEFAULT_VOICE_SPEAKER_2: Final[str] = "IKne3meq5aSn9XLyUdCD"

# Podcast settings
DEFAULT_PODCAST_NAME: Final[str] = "pdf-to-podcast-test"
DEFAULT_DURATION: Final[int] = 2
DEFAULT_SPEAKER_1_NAME: Final[str] = "Alice"
DEFAULT_SPEAKER_2_NAME: Final[str] = "Mark"

# Gradio
GRADIO_CACHE_DIR: Final[str] = get_upload_folder()


def initialize_directories():
    """Initialize all required directories and log file."""
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE_PATH.write_text("", encoding="utf-8")


def setup_logging():
    """Configure logging for the frontend service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH),
            logging.StreamHandler(),
        ],
        force=True,
        encoding="utf-8",
    )
