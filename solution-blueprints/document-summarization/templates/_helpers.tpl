# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "release.name" -}}
{{- $baseName := default .Chart.Name .Values.nameOverride -}}
{{- $baseName | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "release.fullname" -}}
{{- $override := .Values.fullnameOverride -}}
{{- if $override -}}
    {{- $override | trunc 63 | trimSuffix "-" -}}
{{- else -}}
    {{- $name := include "release.name" . -}}
    {{- $release := .Release.Name -}}
    {{- if eq $release "release-name" -}}
        {{- $ts := now | date "20060102-1504" -}}
        {{- printf "%s-%s" $name $ts | lower | trunc 63 | trimSuffix "-" -}}
    {{- else -}}
        {{- printf "%s-%s" $name $release | trunc 63 | trimSuffix "-" -}}
    {{- end -}}
{{- end -}}
{{- end -}}

{{- define "container.env" -}}
- name: LLM_ENDPOINT
  {{/* LLM Service Configuration */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.llm)
        "Release" .Release
        "Chart" (dict "Name" "llm")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}

{{/* Whisper (ASR) Configuration */}}
{{- $whisperValues := index .Values "whisper" | default dict -}}
{{- $whisperPort := index $whisperValues "service" "port" | default "7066" -}}
{{- $whisperCtx := dict "Values" (merge (dict) .Values.whisper) "Release" .Release "Chart" (dict "Name" "whisper") -}}

- name: ASR_SERVICE_HOST_IP
  value: {{ include "whisper.fullname" $whisperCtx | default "whisper" | quote }}
- name: ASR_SERVICE_PORT
  value: {{ $whisperPort | quote }}

{{/* Token Constraints */}}
- name: MAX_INPUT_TOKENS
  value: {{ .Values.maxInputTokens | default "8192" | quote }}
- name: MAX_TOTAL_TOKENS
  value: {{ .Values.maxTotalTokens | default "16384" | quote }}

{{/* Network Proxies */}}
{{- $global := .Values.global -}}
- name: http_proxy
  value: {{ $global.http_proxy | default "" | quote }}
- name: https_proxy
  value: {{ $global.https_proxy | default "" | quote }}
- name: no_proxy
  value: {{ $global.no_proxy | default "" | quote }}

{{/* Custom Environment Variables */}}
{{- $extraEnv := .Values.env_vars | default dict -}}
{{- range $key, $val := $extraEnv }}
- name: {{ $key }}
  {{- if kindIs "string" $val }}
  value: {{ $val | quote }}
  {{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ $val.name }}
      key: {{ $val.key }}
  {{- end }}
{{- end }}
{{- end }}

{{- define "container.volumeMounts" -}}
- {mountPath: "/tmp", name: "tmp"}
{{- end -}}

{{- define "container.volumes" -}}
- name: "tmp"
  emptyDir: {}
{{- end -}}
