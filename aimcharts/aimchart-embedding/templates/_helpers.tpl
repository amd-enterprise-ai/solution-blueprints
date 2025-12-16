# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/* Generic helpers for the embedding chart */}}

{{- define "aim-embedding.release.name" -}}
{{- default "aim-embedding" .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aim-embedding.release.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "aim-embedding.container.resources" -}}
{{- if .resources }}
{{- toYaml .resources }}
{{- else }}
{}
{{- end }}
{{- end -}}

{{- define "aim-embedding.container.env" -}}
{{- $defaultEnv := dict "HF_HOME" "/workload/.cache/huggingface" "INFINITY_ANONYMOUS_USAGE_STATS" "0" }}
{{- $envVars := .env_vars | default $defaultEnv }}
{{- range $key, $value := $envVars }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
- name: "INFINITY_MODEL_ID"
  value: {{ .model | default "intfloat/multilingual-e5-large-instruct" | quote }}
{{- end -}}

{{- define "aim-embedding.container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /dev/shm
  name: dshm
{{- end -}}

{{- define "aim-embedding.container.volumes" -}}
{{- $storage := .storage | default dict }}
{{- $ephemeral := $storage.ephemeral | default dict }}
{{- $dshm := $storage.dshm | default dict }}
- name: ephemeral-storage
  emptyDir:
    sizeLimit: {{ $ephemeral.quantity | default "64Gi" }}
- name: dshm
  emptyDir:
    medium: Memory
    sizeLimit: {{ $dshm.sizeLimit | default "16Gi" }}
{{- end -}}

{{/*
The URL of the Embedding service can be constructed with this template function.
*/}}
{{- define "aim-embedding.url" -}}
{{- if not .Values.existingService -}}
http://{{ include "aim-embedding.release.fullname" . }}:{{ .Values.deployment.ports.http }}
{{- else -}}
{{- if hasPrefix "http" .Values.existingService -}}
{{ .Values.existingService }}
{{- else -}}
http://{{ .Values.existingService }}
{{- end -}}
{{- end -}}
{{- end -}}
