<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# ChromaDB Chart

This chart deploys a ChromaDB server.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| image.repository | string | "chromadb/chroma" | Image repository |
| image.tag | string | "1.3.5" | Image tag |
| persistence.enabled | bool | true | Enable persistence |
| persistence.size | string | "10Gi" | Size of the PVC |
