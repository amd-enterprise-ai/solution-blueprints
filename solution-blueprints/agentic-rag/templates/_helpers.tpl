# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/* Standard Release Helpers */}}
{{- define "release.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "release.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "release.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* URL Helper for MCP Server (Internal Cluster DNS) */}}
{{- define "mcp-server.url" -}}
http://{{ include "release.fullname" . }}-knowledge-mcp:{{ .Values.knowledgeMcp.port }}/sse
{{- end -}}

{{/*
URL for ChromaDB - honours chromadb.existingService when set (mirrors aim-chromadb.url logic).
Use CHROMADB_URL env var so backend.py prefers the full URL over CHROMADB_HOST/PORT.
*/}}
{{- define "chromadb.url" -}}
{{- if .Values.chromadb.existingService -}}
{{- if hasPrefix "http" .Values.chromadb.existingService -}}
{{- .Values.chromadb.existingService -}}
{{- else -}}
http://{{ .Values.chromadb.existingService }}
{{- end -}}
{{- else -}}
http://{{ .Release.Name }}-chromadb:{{ .Values.chromadb.deployment.ports.http }}
{{- end -}}
{{- end -}}

{{/*
Base URL for the Embedding service - honours embedding.existingService when set (mirrors aim-embedding.url logic).
Append /v1/embeddings in the Deployment template for the vLLM OpenAI-compatible API path.
*/}}
{{- define "embedding.baseUrl" -}}
{{- if .Values.embedding.existingService -}}
{{- if hasPrefix "http" .Values.embedding.existingService -}}
{{- .Values.embedding.existingService -}}
{{- else -}}
http://{{ .Values.embedding.existingService }}
{{- end -}}
{{- else -}}
http://{{ .Release.Name }}-aimchart-embedding:{{ dig "deployment" "ports" "http" 7997 .Values.embedding }}
{{- end -}}
{{- end -}}
