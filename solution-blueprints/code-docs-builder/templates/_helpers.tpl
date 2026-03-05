# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "codedocs.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "codedocs.llm.url" -}}
{{- if not .Values.llm.existingService -}}
{{- printf "http://%s-%s" .Values.llm.nameOverride .Release.Name -}}
{{- else -}}
{{- if hasPrefix "http" .Values.llm.existingService -}}
{{ .Values.llm.existingService }}
{{- else -}}
http://{{ .Values.llm.existingService }}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "codedocs.backendUrl" -}}
http://{{ include "codedocs.fullname" . }}-backend:{{ .Values.backend.port }}
{{- end -}}
