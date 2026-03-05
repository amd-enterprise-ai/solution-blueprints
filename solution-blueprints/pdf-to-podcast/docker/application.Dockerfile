# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.12-slim

# Environment setup
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (including docling dependencies for celery-worker)
RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        curl \
        wget \
        git \
        procps \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
        libleptonica-dev \
        libtesseract-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copy requirements and install Python dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir docling==2.64.1 --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu

# Copy application files
COPY app .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ws", "auto"]
