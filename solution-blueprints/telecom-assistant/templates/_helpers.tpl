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

# Build a service name for a component
{{- define "release.componentName" -}}
{{- $root := index . "root" -}}
{{- $name := index . "name" -}}
{{- printf "%s-%s" (include "release.fullname" $root) $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

# Container environment variables helper with tpl rendering
{{- define "container.env" -}}
{{- $root := .root -}}
{{- range $key, $value := .env }}
{{- if or (typeIs "string" $value) (kindIs "int" $value) (kindIs "float64" $value) (kindIs "bool" $value) }}
- name: {{ $key }}
  value: {{ tpl (printf "%v" $value) $root | quote }}
{{- else if and (kindIs "map" $value) (hasKey $value "name") (hasKey $value "key") }}
- name: {{ $key }}
  valueFrom:
    secretKeyRef:
      name: {{ $value.name }}
      key: {{ $value.key }}
{{- else }}
{{- fail (printf "env %s must be string/number/bool or secretKeyRef" $key) }}
{{- end }}
{{- end }}
{{- end -}}

# Container volume mounts helper
{{- define "container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /dev/shm
  name: dshm
{{- end -}}

# Container volumes helper
{{- define "container.volumes" -}}
{{- $root := .root -}}
{{- if $root.Values.storage.ephemeral.storageClassName -}}
- ephemeral:
    volumeClaimTemplate:
      spec:
        {{- if $root.Values.storage.ephemeral.accessModes }}
        accessModes: {{ $root.Values.storage.ephemeral.accessModes }}
        {{- else }}
        accessModes:
          - ReadWriteOnce
        {{- end }}
        resources:
          requests:
            storage: {{ $root.Values.storage.ephemeral.quantity }}
        storageClassName: {{ $root.Values.storage.ephemeral.storageClassName }}
  name: ephemeral-storage
{{- else }}
- emptyDir:
    sizeLimit: {{ $root.Values.storage.ephemeral.quantity }}
  name: ephemeral-storage
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ $root.Values.storage.dshm.sizeLimit }}
  name: dshm
{{- if .extraVolumes }}
{{ toYaml .extraVolumes | nindent 0 }}
{{- end }}
{{- end -}}

{{- define "telecom.serviceUrls" -}}
{{- $ := .root -}}
stt:       {{ include "aimchart-qwen-asr.url" (dict "Values" $.Values.stt       "Release" $.Release "Chart" (dict "Name" "stt"))       | trim | quote }}
llm:       {{ include "aimchart-llm.url"      (dict "Values" $.Values.llm       "Release" $.Release "Chart" (dict "Name" "llm"))       | trim | quote }}
tts:       {{ include "aimchart-qwen-tts.url" (dict "Values" $.Values.tts       "Release" $.Release "Chart" (dict "Name" "tts"))       | trim | quote }}
chromadb:  {{ include "aim-chromadb.url"      (dict "Values" $.Values.chromadb  "Release" $.Release "Chart" (dict "Name" "chromadb"))  | trim | quote }}
embedding: {{ include "aim-embedding.url"     (dict "Values" $.Values.embedding "Release" $.Release "Chart" (dict "Name" "embedding")) | trim | quote }}
vlm:       {{ include "aimchart-llm.url"      (dict "Values" $.Values.vlm       "Release" $.Release "Chart" (dict "Name" "vlm"))       | trim | quote }}
{{- end -}}

{{- define "telecom.waitHttp" -}}
- name: wait-for-{{ .name }}
  image: curlimages/curl:8.18.0
  command: ["sh", "-c"]
  args:
    - |
      echo "Waiting for {{ .name }} ({{ .url }})..."
      until curl -s -f -o /dev/null "{{ .url }}"; do sleep 5; done
      echo "{{ .name }} is up"
{{- end -}}

{{- define "telecom.waitTcp" -}}
- name: wait-for-{{ .name }}
  image: busybox:1.36
  command: ["sh", "-c"]
  args:
    - |
      echo "Waiting for {{ .name }} ({{ .host }}:{{ .port }})..."
      until nc -z {{ .host }} {{ .port }}; do sleep {{ .interval | default 5 }}; done
      echo "{{ .name }} is up"
{{- end -}}
