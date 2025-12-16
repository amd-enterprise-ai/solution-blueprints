<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Embedding Chart

This chart deploys an Infinity embedding server.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| image | string | "michaelf34/infinity:0.0.70-amd-gfx942" | Image repository and tag |
| model | string | "intfloat/multilingual-e5-large-instruct" | Embedding model to use |
| gpus | int | 0 | Number of GPUs to request |
