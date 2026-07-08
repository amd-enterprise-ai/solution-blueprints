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

# create a filled in version of .Values with the platform-specific values
# .Values.platform takes priority over .Values.global.platform
{{- define "aimchart-embedding.platformValues" -}}
{{- $global := .Values.global | default dict -}}
{{- $p := coalesce .Values.platform $global.platform "instinct" -}}
{{- mergeOverwrite (index .Values.platformDefaults $p | deepCopy) (deepCopy .Values) | toYaml -}}
{{- end -}}

{{- define "aim-embedding.container.resources" -}}
{{- if .resources }}
{{- toYaml .resources }}
{{- else }}
{}
{{- end }}
{{- end -}}

{{- define "aim-embedding.container.env" -}}
{{- range $key, $value := .Values.env_vars }}
{{- if (typeIs "string" $value) }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- else if and $value (kindIs "map" $value) (hasKey $value "name") (hasKey $value "key") }}
- name: {{ $key }}
  valueFrom:
    secretKeyRef:
      name: {{ $value.name }}
      key: {{ $value.key }}
{{- else }}
- name: {{ $key }}
  value: {{ $value | toString | quote }}
{{- end }}
{{- end }}
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
http://{{ include "aim-embedding.release.fullname" . }}:{{ dig "deployment" "ports" "http" 7997 .Values }}
{{- else -}}
{{- if hasPrefix "http" .Values.existingService -}}
{{ .Values.existingService }}
{{- else -}}
http://{{ .Values.existingService }}
{{- end -}}
{{- end -}}
{{- end -}}
