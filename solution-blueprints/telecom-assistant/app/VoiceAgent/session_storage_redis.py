# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis
from settings import settings

logger = logging.getLogger(__name__)


class SessionFileStoreRedis:
    def __init__(self):
        self.redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        if settings.redis_password:
            self.redis_url = (
                f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            )
        self.ttl = 300
        self._redis: Optional[redis.Redis] = None

    @staticmethod
    def _sanitize_for_log(value: Optional[str]) -> str:
        if value is None:
            return ""
        return str(value).replace("\r", "").replace("\n", "")

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        return self._redis

    async def add_file(
        self, room_name: str, filename: str, content_type: str, data: bytes, description: Optional[str] = None
    ) -> str:
        r = await self._get_redis()
        key = f"session_files:{room_name}"
        file_id = f"{room_name}_{int(asyncio.get_event_loop().time() * 1000)}_{filename}"

        file_data = {
            "id": file_id,
            "filename": filename,
            "content_type": content_type,
            "description": description,
            "uploaded_at": asyncio.get_event_loop().time(),
        }

        await r.hset(key, file_id, json.dumps(file_data))
        await r.expire(key, self.ttl)
        safe_filename = self._sanitize_for_log(filename)
        safe_room_name = self._sanitize_for_log(room_name)
        logger.info(f"Added file {safe_filename} to Redis room {safe_room_name}")
        return file_id

    async def get_files(self, room_name: str) -> List[Dict]:
        r = await self._get_redis()
        key = f"session_files:{room_name}"
        files_data = await r.hgetall(key)
        if not files_data:
            return []
        files = [json.loads(f) for f in files_data.values()]
        files.sort(key=lambda x: x.get("uploaded_at", 0))
        return files

    async def get_last_file(self, room_name: str) -> Optional[Dict]:
        files = await self.get_files(room_name)
        return files[-1] if files else None

    async def clear_files(self, room_name: str):
        r = await self._get_redis()
        key = f"session_files:{room_name}"
        await r.delete(key)
        safe_room_name = self._sanitize_for_log(room_name)
        logger.info(f"Cleared files for room {safe_room_name}")

    async def save_session_summary(self, room_name: str, summary: str) -> None:
        """Save session summary before rating is collected."""
        r = await self._get_redis()
        key = f"session_summary:{room_name}"
        await r.setex(
            key,
            86400,  # TTL: 24 hours
            json.dumps(
                {
                    "room_name": room_name,
                    "summary": summary,
                    "created_at": datetime.utcnow().isoformat(),
                }
            ),
        )

    async def save_session_rating(self, room_name: str, rating: int, user_id: str = None) -> dict:
        """
        Save user rating linked to session summary.
        Returns the full record that was saved.
        """
        r = await self._get_redis()
        summary_key = f"session_summary:{room_name}"
        raw = await r.get(summary_key)
        summary_data = json.loads(raw) if raw else {}

        record = {
            "room_name": room_name,
            "user_id": user_id or summary_data.get("user_id") or "anonymous",
            "summary": summary_data.get("summary", ""),
            "rating": rating,
            "created_at": summary_data.get("created_at", datetime.utcnow().isoformat()),
            "rated_at": datetime.utcnow().isoformat(),
        }

        # Save rating record with 30-day TTL
        rating_key = f"session_rating:{room_name}"
        await r.setex(rating_key, 2592000, json.dumps(record))

        # Also push to a list so you can retrieve all ratings later
        await r.lpush("all_session_ratings", json.dumps(record))

        safe_room_name = self._sanitize_for_log(room_name)
        logger.info(f"Session rating saved: room={safe_room_name} rating={rating}")
        return record


session_file_store = SessionFileStoreRedis()
