# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis
from settings import settings

logger = logging.getLogger(__name__)


class FileNotifier:
    def __init__(self):
        self.redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        if settings.redis_password:
            self.redis_url = (
                f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            )
        self._pubsubs: dict[str, redis.client.PubSub] = {}
        self._redis: Optional[redis.Redis] = None

    def _sanitize_for_log(self, value: str) -> str:
        return value.replace("\r", "").replace("\n", "")

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await redis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis

    async def notify(self, room_name: str, file_id: str, description: Optional[str] = None) -> None:
        r = await self._get_redis()
        channel = f"file_notify:{room_name}"
        data = json.dumps(
            {"file_id": file_id, "description": description, "timestamp": asyncio.get_event_loop().time()}
        )
        await r.publish(channel, data)
        logger.info(f"Published notification to {self._sanitize_for_log(channel)}")

    async def subscribe(self, room_name: str) -> None:
        if room_name in self._pubsubs:
            return
        r = await self._get_redis()
        pubsub = r.pubsub()
        channel = f"file_notify:{room_name}"
        await pubsub.subscribe(channel)
        self._pubsubs[room_name] = pubsub
        logger.info(f"Subscribed to {self._sanitize_for_log(channel)}")

    async def unsubscribe(self, room_name: str) -> None:
        pubsub = self._pubsubs.pop(room_name, None)
        if pubsub is not None:
            channel = f"file_notify:{room_name}"
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.info(f"Unsubscribed from {self._sanitize_for_log(channel)}")

    async def wait_for_file(self, room_name: str, timeout: float = 30.0) -> Optional[dict]:
        if room_name not in self._pubsubs:
            await self.subscribe(room_name)

        pubsub = self._pubsubs.get(room_name)
        if pubsub is None:
            logger.error("Failed to create pubsub subscription")
            return None

        try:
            message = await pubsub.get_message(timeout=timeout, ignore_subscribe_messages=True)
            if message and message["type"] == "message":
                return json.loads(message["data"])
        except asyncio.TimeoutError:
            logger.debug(
                f"Timed out waiting for file notification in room '{self._sanitize_for_log(room_name)}' after {timeout}s"
            )
        return None


notifier = FileNotifier()


async def notify_agent_new_file(room_name: str, file_id: str, description: Optional[str] = None) -> None:
    await notifier.notify(room_name, file_id, description)


async def wait_for_new_file(room_name: str, timeout: float = 10.0) -> Optional[dict]:
    return await notifier.wait_for_file(room_name, timeout)


async def cleanup_room(room_name: str) -> None:
    """Call this when an agent leaves a room to release its Redis pubsub subscription."""
    await notifier.unsubscribe(room_name)
