# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/*
The URL can be constructed with this template function.
To use this function, build a context with .Values, .Release, and .Chart metadata.
*/}}
{{- define "aimchart-qwen-tts.url" -}}
{{ if not .Values.existingService -}}
http://{{ include "aimchart-qwen-tts.release.fullname" . }}/v1
{{- else -}}
{{- if hasPrefix "http" .Values.existingService -}}
{{ .Values.existingService }}/v1
{{- else -}}
http://{{ .Values.existingService }}/v1
{{- end -}}
{{- end -}}
{{- end -}}
