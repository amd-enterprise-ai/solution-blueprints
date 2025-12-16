# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/*
The URL of the LLM can be constructed with this template function.
To use this function, build a context that has the right .Values, .Release, and .Chart metadata.
NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
Example:
{{- $sub := dict
      "Values" (merge (dict) .Values.llm)
      "Release" .Release
      "Chart" (dict "Name" "llm")
-}}
*/}}
{{- define "aimchart-llm.url" -}}
{{ if not .Values.existingService -}}
http://{{ include "aimchart-llm.release.fullname" . }}/v1
{{- else -}}
{{ if hasPrefix .Values.existingService "http" }}
{{ .Values.existingService }}/v1
{{- else -}}
http://{{ .Values.existingService }}/v1
{{- end -}}
{{- end -}}
{{- end -}}
