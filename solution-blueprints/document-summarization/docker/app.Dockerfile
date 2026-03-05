# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.11-slim

ENV HOME=/home/user
WORKDIR $HOME

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash user && \
    mkdir -p $HOME && \
    chown -R user:user $HOME

# Install Python dependencies (app + shared components)
COPY ./app/requirements.txt .
COPY ./app/components/requirements.txt ./components/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r components/requirements.txt

# Copy application code
COPY --chown=user:user ./app/docsum.py $HOME/docsum.py
COPY --chown=user:user ./app/components $HOME/components

ENV PYTHONPATH=$PYTHONPATH:$HOME:$HOME/components

USER user

ENTRYPOINT ["python", "docsum.py"]
