# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Celery client factory for PDF conversion tasks."""


from celery import Celery
from settings import settings

# Create Celery app instance
celery_app = Celery(
    "app",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max runtime
    task_soft_time_limit=3300,  # 55 minutes soft limit
)

# Import tasks to register them with Celery
# This ensures tasks are available when the worker starts
from infrastructure import celery_tasks  # noqa: F401, E402


def get_celery_app() -> Celery:
    """Return a Celery app configured from settings.

    Returns:
        Celery: Configured Celery application instance.
    """
    return celery_app
