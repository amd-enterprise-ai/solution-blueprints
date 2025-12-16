# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{/* Generic helpers for the chromadb chart */}}

{{- define "aim-chromadb.release.name" -}}
{{- default "aim-chromadb" .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aim-chromadb.release.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "aim-chromadb.container.resources" -}}
{{- if .resources }}
{{- toYaml .resources }}
{{- else }}
{}
{{- end }}
{{- end -}}

{{- define "aim-chromadb.container.volumeMounts" -}}
{{- if .persistence.enabled }}
- name: data
  mountPath: /chroma/.chroma/index
{{- end }}
{{- end -}}

{{- define "aim-chromadb.container.volumes" -}}
{{- if .persistence.enabled }}
- name: data
  persistentVolumeClaim:
    claimName: {{ include "aim-chromadb.release.fullname" . }}
{{- end }}
{{- end -}}

{{/*
The URL of the ChromaDB service can be constructed with this template function.
*/}}
{{- define "aim-chromadb.url" -}}
{{- if not .Values.existingService -}}
http://{{ include "aim-chromadb.release.fullname" . }}:{{ .Values.deployment.ports.http }}
{{- else -}}
{{- if hasPrefix "http" .Values.existingService -}}
{{ .Values.existingService }}
{{- else -}}
http://{{ .Values.existingService }}
{{- end -}}
{{- end -}}
{{- end -}}
