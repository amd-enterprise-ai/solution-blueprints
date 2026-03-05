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
{{- $name := .name -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /dev/shm
  name: dshm
{{- if .extraVolumeMounts }}
{{ toYaml .extraVolumeMounts | nindent 0 }}
{{- end }}
{{- end -}}

# Container volumes helper
{{- define "container.volumes" -}}
{{- $root := .root -}}
{{- $name := .name -}}
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
- emptyDir: {}
  name: ephemeral-storage
  sizeLimit: {{ $root.Values.storage.ephemeral.quantity }}
{{- end }}
- emptyDir:
    medium: Memory
    sizeLimit: {{ $root.Values.storage.dshm.sizeLimit }}
  name: dshm
{{- if .extraVolumes }}
{{ toYaml .extraVolumes | nindent 0 }}
{{- end }}
{{- end -}}
