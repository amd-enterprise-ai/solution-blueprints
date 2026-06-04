# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.11-slim

WORKDIR /app

COPY /app/BSSGateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY /app/BSSGateway/main.py .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
