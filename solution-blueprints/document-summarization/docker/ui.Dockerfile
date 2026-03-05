# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Use standard Python image
FROM python:3.11-slim

ENV LANG=C.UTF-8
WORKDIR /home/user

# Copy requirements and install Python dependencies
COPY ./app-ui/requirements.txt /home/user/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r /home/user/requirements.txt

# Copy application code
COPY ./app-ui/docsum_ui_gradio.py /home/user/docsum_ui_gradio.py

# Expose the port that the application will run on
EXPOSE 5173

# Define the command to run the application
CMD ["python", "docsum_ui_gradio.py"]
