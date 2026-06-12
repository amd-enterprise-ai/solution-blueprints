# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# ---- Stage 1: Build the React app ----
FROM node:20-alpine AS frontend-build

WORKDIR /build

# Copy package files first
COPY med_assist_frontend/client/package.json med_assist_frontend/client/package-lock.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the React source
COPY med_assist_frontend/client/ ./

# Build the production bundle
RUN npm run build


# ---- Stage 2: Python server ----
FROM python:3.12-slim

# Environment setup
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copy requirements and install Python dependencies
COPY med_assist_frontend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy Python application files
COPY med_assist_frontend/ .

# Copy the React build output from stage 1
COPY --from=frontend-build /build/dist ./client_dist

EXPOSE 7860

CMD ["uvicorn", "--host", "0.0.0.0", "--port", "7860", "ui:app"]
