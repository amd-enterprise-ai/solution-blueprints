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
agentictesting-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
agentictesting-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

# Container environment variables helper
{{- define "container.env" -}}
- name: OPENAI_API_BASE_URL
  {{/* Build a context that has the right .Values, .Release, and .Chart metadata. */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.llm)
        "Release" .Release
        "Chart" (dict "Name" "llm")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}
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
