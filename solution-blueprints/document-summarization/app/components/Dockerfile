# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Base image for GenAIComps based DM Python applications
# Build: docker build -t dm/comps-base -f Dockerfile .

ARG IMAGE_NAME=python
ARG IMAGE_TAG=3.11-slim

FROM ${IMAGE_NAME}:${IMAGE_TAG} AS base

ENV HOME=/home/user

RUN useradd -m -s /bin/bash user && \
    mkdir -p $HOME && \
    chown -R user $HOME

# get security updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get clean autoclean && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR $HOME

COPY *.py *.txt *.in ./

ARG uvpip='uv pip install --system --no-cache-dir'
RUN pip install --no-cache-dir --upgrade pip setuptools uv && \
    $uvpip -r requirements.txt

COPY mega/ components/mega/
COPY models/ components/models/
COPY __init__.py components/__init__.py
COPY version.py components/version.py

ENV PYTHONPATH=$PYTHONPATH:$HOME:$HOME/components

USER user

ENTRYPOINT ["sh", "-c", "set && ls -la"]
