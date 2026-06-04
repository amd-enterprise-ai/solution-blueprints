# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Release name helper
{{- define "release.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

# Release fullname helper
{{- define "release.fullname" -}}
{{- $currentTime := now | date "20060102-1504" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- if ne .Release.Name "release-name" -}}
{{- include "release.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "release.name" . }}-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

# Container environment variables helper
{{- define "container.env" -}}
- name: LLM_API_BASE_URL
  {{/* Build a context that has the right .Values, .Release, and .Chart metadata. */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.llm)
        "Release" .Release
        "Chart" (dict "Name" "llm")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}
{{- if .Values.llm.apiKeySecretRef }}
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.llm.apiKeySecretRef.name }}
      key: {{ .Values.llm.apiKeySecretRef.key }}
{{- else if .Values.llm.apiKey }}
- name: LLM_API_KEY
  value: {{ .Values.llm.apiKey | quote }}
{{- end }}
{{- if .Values.llm.model }}
- name: LLM_MODEL
  value: {{ .Values.llm.model | quote }}
{{- end }}
{{- range $key, $value := .Values.envVars }}
{{- if (typeIs "string" $value) }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- else }}
- name: {{ $key }}
  valueFrom:
    secretKeyRef:
      name: {{ $value.name }}
      key: {{ $value.key }}
{{- end }}
{{- end }}
{{- end -}}
