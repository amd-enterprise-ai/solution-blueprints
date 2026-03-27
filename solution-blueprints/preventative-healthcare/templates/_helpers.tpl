# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Release name helper
{{- define "release.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

# Release fullname helper
{{- define "release.fullname" -}}
{{- $currentTime := now | date "20060102-1504" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- if ne .Release.Name "release-name" -}}
{{- include "release.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "release.name" . }}-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

# Container resources helper
{{- define "container.resources" -}}
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

# Container environment variables helper (LLM URL from openaiBaseUrl or llm subchart / existingService)
{{- define "container.env" -}}
- name: PYTHONPATH
  value: /workload/mount
{{- $baseUrl := .Values.openaiBaseUrl }}
{{- if not $baseUrl }}
  {{- $bundled := .Values.llm.enabled | default true }}
  {{- if $bundled }}
  {{- $sub := dict "Values" (omit .Values.llm "enabled") "Release" .Release "Chart" (dict "Name" "llm") }}
  {{- $baseUrl = include "aimchart-llm.url" $sub }}
  {{- else if .Values.llm.existingService }}
  {{- if hasPrefix "http" .Values.llm.existingService }}
  {{- $baseUrl = .Values.llm.existingService }}
  {{- else }}
  {{- $baseUrl = printf "http://%s" .Values.llm.existingService }}
  {{- end }}
  {{- else }}
  {{- fail "If llm.enabled is false, set llm.existingService or openaiBaseUrl." }}
  {{- end }}
{{- end }}
- name: OPENAI_API_BASE_URL
  value: {{ $baseUrl | quote }}
- name: OPENAI_BASE_URL
  value: {{ $baseUrl | quote }}
- name: OPENAI_API_KEY
  value: {{ .Values.openaiApiKey | quote }}
{{- range $key, $value := .Values.env_vars }}
{{- if (typeIs "string" $value) }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- else }}
- name: {{ $key }}
  valueFrom:
    secretKeyRef:
      name: {{ $value.name }}
      key: {{ $value.key }}
{{- end }}
{{- end }}
{{- end -}}

# Container volume mounts helper (ConfigMap is read-only; app runs from writable copy)
{{- define "container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /workload/mount
  name: app-files
- mountPath: /workload/config-src
  name: workload-config
  readOnly: true
- mountPath: /workload/mount/prompts_healthcare
  name: prompts-config
  readOnly: true
- mountPath: /dev/shm
  name: dshm
{{- end -}}

# Container volumes helper
{{- define "container.volumes" -}}
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
- emptyDir: {}
  name: ephemeral-storage
  sizeLimit: {{ .Values.storage.ephemeral.quantity }}
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ .Values.storage.dshm.sizeLimit }}
  name: dshm
- emptyDir: {}
  name: app-files
- configMap:
    name: {{ include "release.fullname" . }}
  name: workload-config
- configMap:
    name: {{ include "release.fullname" . }}-prompts
  name: prompts-config
{{- end -}}
