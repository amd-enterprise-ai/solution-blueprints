# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Base URL helper
{{- define "aimchart-llm.httpRoute.baseUrl" -}}
{{- $projectId := default "project_id" .Values.metadata.project_id -}}
{{- $userId := default "user_id" .Values.metadata.user_id -}}
{{- $workloadId := default (include "aimchart-llm.release.fullname" .) .Values.metadata.workload_id -}}
{{- printf "/%s/%s/%s" $projectId $userId $workloadId }}
{{- end -}}

# Release name helper
{{- define "aimchart-llm.release.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

# Release fullname helper
{{- define "aimchart-llm.release.fullname" -}}
{{- $currentTime := now | date "20060102-1504" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- if ne .Release.Name "release-name" -}}
{{- include "aimchart-llm.release.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "aimchart-llm.release.name" . }}-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

# Configmap name helper
{{- define "aimchart-llm.configmap.name" -}}
{{- print (include "aimchart-llm.release.fullname" .) "-custom-profiles" | trunc 63 }}
{{- end -}}

# Container resources helper
{{- define "aimchart-llm.container.resources" -}}
requests:
  memory: "{{ max (mul .Values.gpus .Values.memory_per_gpu) 4 }}Gi"
  cpu: "{{ max (mul .Values.gpus .Values.cpu_per_gpu) 1 }}"
  {{- if .Values.gpus }}
  amd.com/gpu: "{{ .Values.gpus }}"
  {{- end }}
limits:
  memory: "{{ max (mul .Values.gpus .Values.memory_per_gpu) 4 }}Gi"
  cpu: "{{ max (mul .Values.gpus .Values.cpu_per_gpu) 1 }}"
  {{- if .Values.gpus }}
  amd.com/gpu: "{{ .Values.gpus }}"
  {{- end }}
{{- end -}}

# Container environment variables helper
{{- define "aimchart-llm.container.env" -}}
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

# Container volume mounts helper
{{- define "aimchart-llm.container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /dev/shm
  name: dshm
{{ if .Values.customProfiles -}}
- mountPath: /workspace/aim-runtime/profiles/custom
  readOnly: true
  name: custom-profiles
{{- end }}
{{- end -}}

# Container volumes helper
{{- define "aimchart-llm.container.volumes" -}}
{{- if .Values.storage.ephemeral.storageClassName -}}
- ephemeral:
    volumeClaimTemplate:
      spec:
        {{- if .Values.storage.ephemeral.accessModes }}
        accessModes: {{ .Values.storage.ephemeral.accessModes }}
        {{- else }}
        accessModes:
          - ReadWriteOnce
        {{- end }}
        resources:
          requests:
            storage: {{ .Values.storage.ephemeral.quantity }}
        storageClassName: {{ .Values.storage.ephemeral.storageClassName }}
  name: ephemeral-storage
{{- else }}
- emptyDir:
    sizeLimit: {{ .Values.storage.ephemeral.quantity }}
  name: ephemeral-storage
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ .Values.storage.dshm.sizeLimit }}
  name: dshm
{{ if .Values.customProfiles -}}
- name: custom-profiles
  configMap:
    name: {{ include "aimchart-llm.configmap.name" . }}
{{- end }}
{{- end -}}
