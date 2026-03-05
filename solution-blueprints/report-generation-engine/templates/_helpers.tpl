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

# Container environment variables helper
{{- define "container.env" -}}
- name: OPENAI_API_BASE_URL
  {{/* Build a context that has the right .Values, .Release, and .Chart metadata. */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.llm)
        "Release" .Release
        "Chart" (dict "Name" "llm")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}
- name: API_PORT
  value: {{ .Values.deployment.ports.api | quote }}
- name: UI_PORT
  value: {{ .Values.deployment.ports.ui | quote }}
{{- if .Values.config.tavily.apiKey }}
- name: TAVILY_API_KEY
  value: {{ .Values.config.tavily.apiKey | quote }}
{{- end }}
# LLM Configuration (model auto-discovered from vLLM service)
- name: LLM_TEMPERATURE
  value: {{ .Values.config.llm.temperature | quote }}
- name: LLM_MAX_RETRIES
  value: {{ .Values.config.llm.maxRetries | quote }}
# LangSmith Configuration
- name: LANGSMITH_TRACING_ENABLED
  value: {{ .Values.config.langsmith.tracingEnabled | quote }}
- name: LANGSMITH_PROJECT
  value: {{ .Values.config.langsmith.project | quote }}
# Search Configuration
- name: SEARCH_NUMBER_OF_QUERIES
  value: {{ .Values.config.search.numberOfQueries | quote }}
- name: SEARCH_TAVILY_TOPIC
  value: {{ .Values.config.search.tavilyTopic | quote }}
- name: SEARCH_TAVILY_MAX_RESULTS
  value: {{ .Values.config.search.tavilyMaxResults | quote }}
# Generation Configuration
- name: GENERATION_MAX_SECTION_LENGTH
  value: {{ .Values.config.generation.maxSectionLength | quote }}
- name: GENERATION_FINAL_SECTION_LENGTH
  value: {{ .Values.config.generation.finalSectionLength | quote }}
- name: GENERATION_PLANNING_CONTEXT_CHARS
  value: {{ .Values.config.generation.planningContextChars | quote }}
- name: GENERATION_SECTION_CONTEXT_CHARS
  value: {{ .Values.config.generation.sectionContextChars | quote }}
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

# Container volume mounts helper
{{- define "container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /workload/mount
  name: workload-mount
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
- emptyDir:
    sizeLimit: {{ .Values.storage.ephemeral.quantity }}
  name: ephemeral-storage
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ .Values.storage.dshm.sizeLimit }}
  name: dshm
- configMap:
    name: {{ include "release.fullname" . }}
  name: workload-mount
{{- end -}}
