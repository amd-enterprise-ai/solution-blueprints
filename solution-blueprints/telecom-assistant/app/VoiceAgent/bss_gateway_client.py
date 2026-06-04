# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import httpx
from pydantic import BaseModel
from settings import settings


class UserShortResponse(BaseModel):
    """
    Schema for a condensed user profile.

    Attributes:
        user_id (str): The unique identifier of the user in the billing system.
        first_name (str): User's legal first name.
        last_name (str): User's legal last name.
    """

    user_id: str
    first_name: str
    last_name: str


class BSSGatewayClient:
    """
    An asynchronous client for the BSSGateway API.

    Provides an interface to mock third-party billing systems.
    Includes built-in retry logic for resilient communication with the billing backend.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.bssgateway_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=httpx.AsyncHTTPTransport(retries=3),
        )

    async def get_balance(self, user_id: str):
        r = await self.client.get(f"/billing/balance/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_payments(self, user_id: str):
        r = await self.client.get(f"/billing/payments/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_invoices(self, user_id: str):
        r = await self.client.get(f"/billing/invoices/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_user_by_phrase(self, pass_phrase: str) -> UserShortResponse:
        r = await self.client.get(f"/users/user/{pass_phrase}")
        r.raise_for_status()
        return UserShortResponse(**r.json())

    async def get_user_role(self, user_id: str) -> dict:
        r = await self.client.get(f"/users/role/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_user_plan(self, user_id: str) -> dict:
        r = await self.client.get(f"/users/plan/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_plan_quotas(self, user_id: str, plan: str):
        r = await self.client.get(f"/users/plan/{user_id}/{plan}/quotas")
        r.raise_for_status()
        return r.json()

    async def add_extra_quota(self, user_id: str, plan: str, quota: int):
        r = await self.client.patch(
            f"/users/plan/{user_id}/{plan}/quotas",
            json={"quota": quota},
        )
        r.raise_for_status()
        return r.json()
