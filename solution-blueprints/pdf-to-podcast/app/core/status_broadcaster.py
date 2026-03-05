# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""WebSocket broadcaster for task status updates."""


import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class StatusBroadcaster:
    """Manage WebSocket connections and push status updates."""

    def __init__(self) -> None:
        """Initialize the broadcaster.

        Returns:
            None
        """
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, task_id: str) -> None:
        """Register a WebSocket for a task.

        Args:
            websocket (WebSocket): Client WebSocket.
            task_id (str): Task identifier to subscribe.

        Returns:
            None
        """
        await websocket.accept()
        async with self._lock:
            self._connections[task_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, task_id: str) -> None:
        """Remove a WebSocket from the task set.

        Args:
            websocket (WebSocket): Client WebSocket.
            task_id (str): Task identifier to unsubscribe.

        Returns:
            None
        """
        async with self._lock:
            if task_id in self._connections and websocket in self._connections[task_id]:
                self._connections[task_id].remove(websocket)
                if not self._connections[task_id]:
                    del self._connections[task_id]

    async def publish(self, task_id: str, payload: dict[str, Any]) -> None:
        """Send payload to all connected clients for the task.

        Args:
            task_id (str): Task identifier.
            payload (dict[str, Any]): Status payload to broadcast.

        Returns:
            None
        """
        async with self._lock:
            connections = list(self._connections.get(task_id, set()))

        to_remove: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except WebSocketDisconnect:
                to_remove.append(websocket)
            except Exception:
                to_remove.append(websocket)

        if to_remove:
            async with self._lock:
                for ws in to_remove:
                    self._connections[task_id].discard(ws)
                if task_id in self._connections and not self._connections[task_id]:
                    del self._connections[task_id]
