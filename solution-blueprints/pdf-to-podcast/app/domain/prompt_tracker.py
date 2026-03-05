# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Lightweight prompt tracker that writes to local storage."""


import json
import time
from dataclasses import asdict, dataclass

from infrastructure.storage import LocalStorage


@dataclass
class ProcessingStep:
    """Single LLM interaction."""

    step_name: str
    prompt: str
    response: str
    model: str
    timestamp: float


class PromptTracker:
    """Persist prompt/response history for a task."""

    def __init__(self, task_id: str, user_id: str, storage: LocalStorage) -> None:
        self._task_id = task_id
        self._user_id = user_id
        self._storage = storage
        self._steps: dict[str, ProcessingStep] = {}

    def track(self, step_name: str, prompt: str, model: str, response: str | None = None) -> None:
        """Record a prompt and optional response.

        Args:
            step_name (str): Name of the step.
            prompt (str): Prompt text sent to the model.
            model (str): Model identifier.
            response (str | None): Optional response content.
        """
        self._steps[step_name] = ProcessingStep(
            step_name=step_name,
            prompt=prompt,
            response=response or "",
            model=model,
            timestamp=time.time(),
        )
        if response:
            self._flush()

    def update_result(self, step_name: str, response: str) -> None:
        """Update response for an existing step and persist.

        Args:
            step_name (str): Step name to update.
            response (str): Response text to store.
        """
        if step_name not in self._steps:
            return
        self._steps[step_name].response = response
        self._flush()

    def _flush(self) -> None:
        """Write tracker data to storage."""
        payload = {"steps": [asdict(step) for step in self._steps.values()]}
        self._storage.store_file(
            user_id=self._user_id,
            task_id=self._task_id,
            content=json.dumps(payload).encode(),
            filename=f"{self._task_id}_prompt_tracker.json",
            content_type="application/json",
        )
