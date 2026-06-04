# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import base64
import logging
from typing import Any

import httpx
from settings import settings

logger = logging.getLogger(__name__)


class LibreDeskClient:

    def __init__(self):
        self.client = httpx.AsyncClient(base_url=settings.libredesk_url, timeout=httpx.Timeout(30.0))

    async def create_ticket(self, title: str, body: str, customer: str) -> Any:
        if not settings.libredesk_token:
            logger.error("Libredesk token is not configured")
            return {"error": "Libredesk token is not configured"}

        credentials = base64.b64encode(settings.libredesk_token.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

        payload = {
            "subject": f"{title}. UserId: {customer}",
            "content": body,
            "inbox_id": settings.libredesk_inbox_id,
            "contact_email": "support@support.com",
            "initiator": "agent",
            "first_name": "chat",
            "last_name": "bot",
        }

        logger.info(f"URL: {settings.libredesk_url}/api/v1/conversations")
        logger.info(f"JSON Payload: {payload}")

        response = await self.client.post("/api/v1/conversations", headers=headers, json=payload)
        response.raise_for_status()

        return response.json()
