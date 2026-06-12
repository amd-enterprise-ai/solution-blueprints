# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "fintech.complexName" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}-aimsb-fintech-onboarding
{{- end -}}

{{- define "llm.vlmApiKey" -}}
{{- .Values.secrets.VLM_TOKEN -}}
{{- end -}}

{{- define "llm.vlmModelName" -}}
{{- .Values.secrets.VLM_MODEL_NAME -}}
{{- end -}}

{{- define "release.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "release.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- if ne .Release.Name "release-name" -}}
{{- include "release.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "release.name" . | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /workload/mount
  name: workload-mount
- mountPath: /dev/shm
  name: dshm
{{- end -}}

{{- define "container.volumes" -}}
- emptyDir:
    medium: Memory
    sizeLimit: {{ .Values.storage.dshm.sizeLimit }}
  name: dshm
- emptyDir: {}
  name: workload-mount
- emptyDir: {}
  name: ephemeral-storage
{{- end -}}

{{- define "container.resources" -}}
requests:
  memory: {{ .Values.resources.requests.memory | quote }}
  cpu: {{ .Values.resources.requests.cpu | quote }}
limits:
  memory: {{ .Values.resources.limits.memory | quote }}
  cpu: {{ .Values.resources.limits.cpu | quote }}
{{- end -}}

{{- define "backend.url" -}}
http://{{ include "fintech.complexName" . }}-backend:{{ .Values.ports.fintech }}
{{- end -}}
