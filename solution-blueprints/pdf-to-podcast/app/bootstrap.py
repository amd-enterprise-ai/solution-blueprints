# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Application bootstrap: initialize shared services once."""

from core.status_broadcaster import StatusBroadcaster
from core.task_store import TaskStore
from domain.podcast_service import PodcastService
from domain.scenario_runner import ScenarioRunner
from domain.tts_runner import TtsRunner
from infrastructure.pdf_converter import PdfConverter
from infrastructure.storage import LocalStorage

storage = LocalStorage()
broadcaster = StatusBroadcaster()
task_store = TaskStore(broadcaster)
pdf_converter = PdfConverter(task_store, storage)
scenario_runner = ScenarioRunner(task_store, storage)
tts_runner = TtsRunner(task_store)
podcast_service = PodcastService(
    task_store=task_store,
    storage=storage,
    pdf_converter=pdf_converter,
    scenario_runner=scenario_runner,
    tts_runner=tts_runner,
)
