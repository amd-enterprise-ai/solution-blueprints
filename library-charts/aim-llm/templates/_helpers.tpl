# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Base URL helper
{{- define "aim-llm.httpRoute.baseUrl" -}}
{{- $metadataBloc := .metadata | default dict }}
{{- $projectId := default "project_id" $metadataBloc.project_id -}}
{{- $userId := default "user_id" $metadataBloc.user_id -}}
{{- $workloadId := default (include "aim-llm.release.fullname" .) $metadataBloc.workload_id -}}
{{- printf "/%s/%s/%s" $projectId $userId $workloadId }}
{{- end -}}

# Release name helper
{{- define "aim-llm.release.name" -}}
{{- default "aim-llm" .nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

# Release fullname helper
{{- define "aim-llm.release.fullname" -}}
{{- $currentTime := now | date "20060102-1504" -}}
{{- if .fullnameOverride -}}
{{- .fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "aim-llm.release.name" . }}-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

# Container resources helper
{{- define "aim-llm.container.resources" -}}
{{ $_gpus := default 1 .gpus }}
{{ $_memory_per_gpu := default 64 .memory_per_gpu }}
{{ $_cpu_per_gpu := default 4 .cpu_per_gpu }}
requests:
  memory: "{{ max (mul $_gpus $_memory_per_gpu) 4 }}Gi"
  cpu: "{{ max (mul $_gpus $_cpu_per_gpu) 1 }}"
  {{- if $_gpus }}
  amd.com/gpu: "{{ $_gpus }}"
  {{- end }}
limits:
  memory: "{{ max (mul $_gpus $_memory_per_gpu) 4 }}Gi"
  cpu: "{{ max (mul $_gpus $_cpu_per_gpu) 1 }}"
  {{- if $_gpus }}
  amd.com/gpu: "{{ $_gpus }}"
  {{- end }}
{{- end -}}

# Container environment variables helper
{{- define "aim-llm.container.env" -}}
{{- range $key, $value := default dict .env_vars }}
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
{{- define "aim-llm.container.volumeMounts" -}}
- mountPath: /workspace/model-cache
  name: ephemeral-storage
- mountPath: /dev/shm
  name: dshm
{{- end -}}

# Container volumes helper
{{- define "aim-llm.container.volumes" -}}
{{- $storageblock := .storage | default dict }}
{{- $ephemeralblock := $storageblock.ephemeral | default dict }}
{{- $dshmblock := $storageblock.dshm | default dict }}
{{- if $ephemeralblock.storageClassName -}}
- ephemeral:
    volumeClaimTemplate:
      spec:
        {{- if $ephemeralblock.accessModes }}
        accessModes: {{ $ephemeralblock.accessModes }}
        {{- else }}
        accessModes:
          - ReadWriteOnce
        {{- end }}
        resources:
          requests:
            storage: {{ $ephemeralblock.quantity | default "256Gi" }}
        storageClassName: {{ $ephemeralblock.storageClassName }}
  name: ephemeral-storage
{{- else }}
- emptyDir:
    sizeLimit: {{ $ephemeralblock.quantity | default "256Gi" }}
  name: ephemeral-storage
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ $dshmblock.sizeLimit | default "32Gi" }}
  name: dshm
{{- end -}}
