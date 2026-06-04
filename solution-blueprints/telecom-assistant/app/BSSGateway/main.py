# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

"""
    An asynchronous backend for the BSSGateway API.

    Provides an interface to mock third-party billing systems.
    Includes built-in retry logic for resilient communication with the billing backend.
"""
app = FastAPI(title="Mock BSSGateway API")


class BalanceResponse(BaseModel):
    user_id: str
    balance: float
    currency: str


class Payment(BaseModel):
    id: str
    amount: float
    date: str


class Invoice(BaseModel):
    id: str
    amount: float
    status: str


class AddExtraQuotaRequest(BaseModel):
    quota: int = Field(..., gt=0)


class User(BaseModel):
    first_name: str
    last_name: str
    pass_phrase: str
    plan_name: str
    balance: float
    high_speed_quotas: int
    role: str
    currency: str
    payments: List[Payment]
    invoices: List[Invoice]


MOCK_USERS: dict[str, User] = {
    "user1": User(
        first_name="John",
        last_name="Black",
        pass_phrase="milkyway",
        plan_name="Essential Connect",
        balance=125.50,
        high_speed_quotas=5,
        role="user",
        currency="USD",
        payments=[
            Payment(id="pay_1", amount=50.0, date="2024-01-10"),
            Payment(id="pay_2", amount=75.0, date="2024-02-15"),
        ],
        invoices=[
            Invoice(id="inv_1", amount=100.0, status="paid"),
            Invoice(id="inv_2", amount=50.0, status="open"),
        ],
    ),
    "user2": User(
        first_name="Max",
        last_name="White",
        pass_phrase="mars",
        plan_name="Apex Unlimited",
        balance=165.50,
        high_speed_quotas=15,
        currency="USD",
        role="user",
        payments=[
            Payment(id="pay_3", amount=75.0, date="2024-01-10"),
            Payment(id="pay_4", amount=75.5, date="2024-02-15"),
            Payment(id="pay_5", amount=75.5, date="2024-03-15"),
            Payment(id="pay_6", amount=75.5, date="2024-04-15"),
        ],
        invoices=[
            Invoice(id="inv_3", amount=100.0, status="paid"),
            Invoice(id="inv_4", amount=100.0, status="paid"),
            Invoice(id="inv_5", amount=100.0, status="paid"),
            Invoice(id="inv_6", amount=50.0, status="open"),
        ],
    ),
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/users/user/{pass_phrase}")
def get_user(pass_phrase: str) -> dict[str, str]:
    for user_id, data in MOCK_USERS.items():
        if data.pass_phrase == pass_phrase:
            return {
                "user_id": user_id,
                "first_name": data.first_name,
                "last_name": data.last_name,
            }
    raise HTTPException(status_code=404, detail="User not found with this pass phrase")


@app.get("/users/role/{user_id}")
def get_user_role(user_id: str) -> dict[str, str]:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "role": user.role}


@app.get("/users/plan/{user_id}")
def get_user_plan_name(user_id: str) -> dict[str, str]:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "plan_name": user.plan_name}


@app.patch("/users/plan/{user_id}/{plan}/quotas")
def add_extra_quota(user_id: str, plan: str, payload: AddExtraQuotaRequest) -> dict:
    """
    Add extra high_speed_quotas.
    """
    user = _get_user_and_check_plan(user_id, plan)

    current = user.high_speed_quotas
    user.high_speed_quotas = current + payload.quota

    return {
        "user_id": user_id,
        "plan_name": plan,
        "high_speed_quotas": user.high_speed_quotas,
        "added": payload.quota,
    }


@app.get("/users/plan/{user_id}/{plan}/quotas")
def get_plan_quotas(user_id: str, plan: str) -> dict:
    """
    Get high_speed_quotas.
    """
    user = _get_user_and_check_plan(user_id, plan)
    return {
        "user_id": user_id,
        "plan_name": plan,
        "high_speed_quotas": user.high_speed_quotas,
    }


def _get_user_and_check_plan(user_id: str, plan: str) -> User:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.plan_name != plan:
        raise HTTPException(status_code=404, detail="Plan not found for this user")

    return user


@app.get("/billing/balance/{user_id}", response_model=BalanceResponse)
def get_balance(user_id: str) -> BalanceResponse:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return BalanceResponse(user_id=user_id, balance=user.balance, currency=user.currency)


@app.get("/billing/payments/{user_id}", response_model=list[Payment])
def get_payments(user_id: str) -> list[Payment]:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user.payments


@app.get("/billing/invoices/{user_id}", response_model=list[Invoice])
def get_invoices(user_id: str) -> list[Invoice]:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user.invoices


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
