# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from fastapi.responses import JSONResponse


def error_response(type_: str, message: str, status: int, source: str = "infrastructure") -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"type": type_, "message": message, "status": status, "source": source}}
    )
