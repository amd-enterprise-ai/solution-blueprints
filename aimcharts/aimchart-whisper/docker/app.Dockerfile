# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.11-slim

ENV LANG=en_US.UTF-8
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

# Install Python dependencies
ARG ARCH=cpu
COPY --chown=user:user ./app/requirements-${ARCH}.txt /tmp/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools uv && \
    if [ "${ARCH}" = "cpu" ]; then \
        uv pip install --system --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
        uv pip install --system --no-cache-dir -r /tmp/requirements.txt ; \
    else \
        uv pip install --system --no-cache-dir -r /tmp/requirements.txt ; \
    fi

# Copy application code
COPY --chown=user:user ./app/whisper_comps $HOME/whisper_comps
COPY --chown=user:user ./app $HOME/whisper

ENV PYTHONPATH=$PYTHONPATH:$HOME:$HOME/whisper_comps:$HOME/whisper

ENV ASR_MODEL_PATH=openai/whisper-small
ENV DEVICE=cpu
ENV TARGET_LANG=english

USER user
WORKDIR $HOME/whisper

ENTRYPOINT ["uvicorn", "whisper_server:app", "--host", "0.0.0.0", "--port", "7066"]
