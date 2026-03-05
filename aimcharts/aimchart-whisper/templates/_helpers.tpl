# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- /* Chart Name Generators */ -}}
{{- define "whisper.name" -}}
{{- $userOverride := .Values.nameOverride | default .Chart.Name -}}
{{- $userOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "whisper.fullname" -}}
{{- $full := .Values.fullnameOverride -}}
{{- $defName := default .Chart.Name .Values.nameOverride -}}
{{- $release := .Release.Name -}}

{{- if $full -}}
    {{- $full | trunc 63 | trimSuffix "-" -}}
{{- else -}}
    {{- if not (contains $defName $release) -}}
        {{- printf "%s-%s" $release $defName | trunc 63 | trimSuffix "-" -}}
    {{- else -}}
        {{- $release | trunc 63 | trimSuffix "-" -}}
    {{- end -}}
{{- end -}}
{{- end -}}

{{- define "whisper.chart" -}}
{{- .Chart.Name | printf "%s-%s" .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- /* Labeling Logic */ -}}
{{- define "whisper.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/name: {{ include "whisper.name" . }}
{{- end -}}

{{- define "whisper.labels" -}}
{{ include "whisper.selectorLabels" . }}
helm.sh/chart: {{ include "whisper.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end -}}

{{- $g := .Values.global -}}
