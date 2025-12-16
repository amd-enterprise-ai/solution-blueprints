# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM python:3.12

COPY app/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY app/src /app/src
