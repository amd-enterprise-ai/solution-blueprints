# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""FastAPI application for the"""


import logging
import sys

from api.common import router as common_router
from api.routes import router
from fastapi import FastAPI

# Configure logging with simple format
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF to Podcast", version="1.0.0")
app.include_router(common_router)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
