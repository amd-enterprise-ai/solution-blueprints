# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import Event, Thread
from urllib.parse import urljoin

import websockets

from ..settings import WS_MAX_RECONNECT_DELAY, WS_RECONNECT_DELAY, WS_TIMEOUT

log = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Status values for service updates."""

    COMPLETED = "completed"
    FAILED = "failed"
    PROCESSING = "processing"
    PENDING = "pending"


class ServiceType(str, Enum):
    """Service types that can send status updates."""

    PDF = "pdf"
    AGENT = "agent"
    TTS = "tts"


class MessageType(str, Enum):
    """Types of WebSocket messages.

    Backend currently sends only STATUS_UPDATE messages without explicit type field.
    Other types are reserved for future extensions.
    """

    READY_CHECK = "ready_check"  # Connection readiness check
    STATUS_UPDATE = "status_update"  # Service status updates (default from backend)
    HEARTBEAT = "heartbeat"  # Keep-alive messages


@dataclass
class StatusUpdate:
    """Represents a status update from a service."""

    service: str
    status: str
    message: str
    timestamp: datetime

    def __str__(self) -> str:
        """Format status update as string."""
        return f"{self.service}: {self.status} - {self.message}"


class StatusMonitor:
    """
    Monitors podcast generation status via WebSocket connection.

    This class establishes a WebSocket connection to monitor the status of
    podcast generation tasks, handling reconnections and status updates.

    Example:
        ```python
        monitor = StatusMonitor(base_url="http://api.example.com", task_id="123")
        monitor.start()
        try:
            monitor.tts_completed.wait(timeout=300)
        finally:
            monitor.stop()
        ```
    """

    # Supported services
    SUPPORTED_SERVICES: set[str] = {ServiceType.PDF, ServiceType.AGENT, ServiceType.TTS}

    def __init__(
        self,
        base_url: str,
        task_id: str,
        on_status_update: Callable[[StatusUpdate], None] | None = None,
        on_completed: Callable[[], None] | None = None,
        on_failed: Callable[[str, str], None] | None = None,
    ):
        """
        Initialize the status monitor.

        Args:
            base_url: Base URL of the API service (HTTP/HTTPS)
            task_id: Task ID to monitor
            on_status_update: Optional callback for status updates
            on_completed: Optional callback when TTS completes
            on_failed: Optional callback when task fails (service, message)
        """
        self.base_url = base_url
        self.task_id = task_id
        self.ws_url = self._build_ws_url(base_url, task_id)
        self.stop_event = Event()
        self.services = self.SUPPORTED_SERVICES.copy()
        self.last_statuses: dict[str, str | None] = {service: None for service in self.services}
        self.tts_completed = Event()
        self.failed = False
        self.websocket: websockets.ClientConnection | None = None
        self.reconnect_delay = WS_RECONNECT_DELAY
        self.max_reconnect_delay = WS_MAX_RECONNECT_DELAY
        self.ready_event = asyncio.Event()
        self.thread: Thread | None = None

        # Callbacks
        self.on_status_update = on_status_update
        self.on_completed = on_completed
        self.on_failed = on_failed

    @staticmethod
    def _build_ws_url(base_url: str, task_id: str) -> str:
        """
        Convert HTTP/HTTPS URL to WebSocket URL.

        Args:
            base_url: HTTP/HTTPS base URL
            task_id: Task ID for the status endpoint

        Returns:
            WebSocket URL for status monitoring
        """
        if base_url.startswith("https://"):
            ws_base = "wss://" + base_url[8:]
        elif base_url.startswith("http://"):
            ws_base = "ws://" + base_url[7:]
        else:
            # Assume HTTP if no protocol specified
            ws_base = "ws://" + base_url

        return urljoin(ws_base, f"/podcasts/{task_id}/status")

    def _get_time(self) -> str:
        """Get current time formatted as HH:MM:SS."""
        return datetime.now().strftime("%H:%M:%S")

    def start(self) -> None:
        """Start the WebSocket monitoring in a separate thread."""
        if self.thread is not None and self.thread.is_alive():
            log.warning("[%s] Monitor already running", self._get_time())
            return

        self.stop_event.clear()
        self.thread = Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        log.debug("[%s] Status monitor started", self._get_time())

    def stop(self, timeout: float | None = None) -> None:
        """
        Stop the WebSocket monitoring.

        Args:
            timeout: Maximum time to wait for thread to stop (None = wait indefinitely)
        """
        if self.thread is None:
            return

        self.stop_event.set()
        self.thread.join(timeout=timeout)
        self.thread = None
        log.debug("[%s] Status monitor stopped", self._get_time())

    def _run_async_loop(self) -> None:
        """Run the asyncio event loop in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._monitor_status())
        finally:
            loop.close()

    async def _monitor_status(self) -> None:
        """Monitor status via WebSocket with automatic reconnection."""
        while not self.stop_event.is_set():
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    self.reconnect_delay = WS_RECONNECT_DELAY
                    log.info("[%s] Connected to status WebSocket", self._get_time())

                    await self._handle_connection(websocket)

            except websockets.exceptions.ConnectionClosed:
                self.ready_event.clear()
                if not self.stop_event.is_set():
                    log.warning("[%s] WebSocket connection closed, reconnecting...", self._get_time())

            except Exception as e:
                self.ready_event.clear()
                if not self.stop_event.is_set():
                    log.error("[%s] WebSocket error: %s, reconnecting...", self._get_time(), e)

            if not self.stop_event.is_set():
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)

    async def _handle_connection(self, websocket: websockets.ClientConnection) -> None:
        """Handle active WebSocket connection."""
        while not self.stop_event.is_set():
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=WS_TIMEOUT)

                # Parse message to determine type
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                except json.JSONDecodeError:
                    # If not JSON, treat as plain text (for ready_check)
                    msg_type = None

                # Handle ready check messages (can be JSON or plain text)
                if msg_type == MessageType.READY_CHECK or message == "ready_check":
                    if await self._handle_ready_check(websocket, message):
                        continue

                # Handle heartbeat messages
                if msg_type == MessageType.HEARTBEAT:
                    await self._handle_heartbeat(websocket)
                    continue

                # Handle all other message types
                await self._handle_message(message)

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    pong_waiter = await websocket.ping()
                    await pong_waiter
                except Exception:
                    # Connection lost, break to reconnect
                    break

    async def _handle_ready_check(self, websocket: websockets.ClientConnection, message: str) -> bool:
        """
        Handle ready check messages.

        Args:
            websocket: WebSocket connection
            message: Received message

        Returns:
            True if message was a ready check, False otherwise
        """
        try:
            data = json.loads(message)
            if data.get("type") == MessageType.READY_CHECK:
                await websocket.send("ready")
                log.info("[%s] Sent ready acknowledgment", self._get_time())
                return True
        except json.JSONDecodeError:
            # Handle plain text ready_check
            if message == "ready_check":
                await websocket.send("ready")
                log.info("[%s] Sent ready acknowledgment", self._get_time())
                return True
        return False

    async def _handle_heartbeat(self, websocket: websockets.ClientConnection) -> None:
        """
        Handle heartbeat messages to keep connection alive.

        Args:
            websocket: WebSocket connection
        """
        try:
            await websocket.send(json.dumps({"type": MessageType.HEARTBEAT, "response": "pong"}))
            log.debug("[%s] Responded to heartbeat", self._get_time())
        except Exception as e:
            log.warning("[%s] Failed to respond to heartbeat: %s", self._get_time(), e)

    async def _handle_message(self, message: str) -> None:
        """
        Handle incoming WebSocket messages.

        Backend sends messages in format:
        {
            "task_id": str,
            "status": TaskStatus,  # "pending", "processing", "completed", "failed"
            "message": str,
            "services": dict,
            "service": ServiceType | None  # "pdf", "agent", "tts" or None
        }

        Args:
            message: JSON-encoded message
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            # Backend sends status updates without "type" field
            # If no type specified, treat as status update (backend format)
            if msg_type is None:
                # Backend format: has "status" field (and optionally "service" or "services")
                if "status" in data:
                    msg_type = MessageType.STATUS_UPDATE
                else:
                    # Unknown format, log and skip
                    log.warning("[%s] Received message without type or status field: %s", self._get_time(), data)
                    return

            # Handle different message types
            if msg_type == MessageType.STATUS_UPDATE:
                await self._handle_status_update(data)
            elif msg_type == MessageType.HEARTBEAT:
                # Heartbeat is already handled in _handle_connection before calling this method
                log.debug("[%s] Received heartbeat message", self._get_time())
            else:
                log.debug("[%s] Unknown message type: %s", self._get_time(), msg_type)

        except json.JSONDecodeError:
            log.error("[%s] Received invalid JSON: %s", self._get_time(), message)
        except Exception as e:
            log.error("[%s] Error processing message: %s", self._get_time(), e)

    async def _handle_status_update(self, data: dict) -> None:
        """Handle status update messages from backend.

        Backend sends messages in format:
        {
            "task_id": str,
            "status": TaskStatus,  # "pending", "processing", "completed", "failed"
            "message": str,
            "services": dict,
            "service": ServiceType | None  # "pdf", "agent", "tts" or None
        }
        """
        # Backend sends service as string value or None
        service = data.get("service")
        # Backend sends status as string (TaskStatus enum value)
        status = data.get("status", "")
        msg = data.get("message", "")

        # If service is None, this might be an initial status update
        # Check services dict for individual service statuses
        if service is None:
            services_data = data.get("services", {})
            # Process all services that have updates
            for svc_name, svc_data in services_data.items():
                if isinstance(svc_data, dict):
                    svc_status = svc_data.get("status")
                    svc_msg = svc_data.get("message", "")
                    if svc_status and svc_name in self.services:
                        await self._process_service_status(svc_name, svc_status, svc_msg)
            return

        # Process single service update
        if service not in self.services:
            log.debug("[%s] Ignoring update from unknown service: %s", self._get_time(), service)
            return

        await self._process_service_status(service, status, msg)

    async def _process_service_status(self, service: str, status: str, msg: str) -> None:
        """Process status update for a specific service."""
        # Create status update object
        status_update = StatusUpdate(
            service=service,
            status=status,
            message=msg,
            timestamp=datetime.now(),
        )

        # Log if status changed
        current_status_str = str(status_update)
        if current_status_str != self.last_statuses[service]:
            log.info("[%s] %s", self._get_time(), current_status_str)
            self.last_statuses[service] = current_status_str

            # Call status update callback
            if self.on_status_update:
                try:
                    self.on_status_update(status_update)
                except Exception as e:
                    log.error("[%s] Error in status update callback: %s", self._get_time(), e)

        # Handle completion and failure
        if status == ServiceStatus.FAILED:
            self._handle_failure(service, msg)
        elif service == ServiceType.TTS and status == ServiceStatus.COMPLETED:
            self._handle_completion()

    def _handle_failure(self, service: str, message: str) -> None:
        """
        Handle task failure.

        Args:
            service: Service that reported the failure
            message: Failure message
        """
        log.error("[%s] Job failed in %s: %s", self._get_time(), service, message)
        self.failed = True
        self.tts_completed.set()  # Unblock waiters
        self.stop_event.set()

        # Call failure callback
        if self.on_failed:
            try:
                self.on_failed(service, message)
            except Exception as e:
                log.error("[%s] Error in failure callback: %s", self._get_time(), e)

    def _handle_completion(self) -> None:
        """Handle successful TTS completion."""
        self.tts_completed.set()
        self.stop_event.set()

        # Call completion callback
        if self.on_completed:
            try:
                self.on_completed()
            except Exception as e:
                log.error("[%s] Error in completion callback: %s", self._get_time(), e)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
