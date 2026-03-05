# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "router.complexName" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "llm.findModel" -}}
{{- $backend := .backend -}}
{{- $found := dict -}}
{{- $ok := false -}}
{{- range .Values.models }}
{{- if eq .name $backend }}
{{- $_ := set $found "model" . -}}
{{- $_ := set $found "ok" true -}}
{{- end }}
{{- end }}
{{- if not ($found.ok | default false) -}}
{{- fail (printf "Model '%s' not found in values.models" $backend) -}}
{{- end -}}
{{- $found.model | toYaml -}}
{{- end -}}

{{- define "llm.backendBaseUrl" -}}
{{- if .Values.deployDemonstrationLLMs -}}
http://{{ .backend }}-{{ .Release.Name }}
{{- else -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- $model.base_url | trim -}}
{{- end -}}
{{- end -}}

{{- define "llm.backendApiKey" -}}
{{- if .Values.deployDemonstrationLLMs -}}
{{- "" -}}
{{- else -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- default "" $model.api_key -}}
{{- end -}}
{{- end -}}

{{- define "llm.backendModelName" -}}
{{- if .Values.deployDemonstrationLLMs -}}
{{- "" -}}
{{- else -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- default "" $model.model_name -}}
{{- end -}}
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

{{- define "controller.url" -}}
http://{{ include "router.complexName" . }}-router-controller:{{ .Values.ports.routerController }}
{{- end -}}

{{- define "classifier.url" -}}
http://{{ include "router.complexName" . }}-router-classifier:{{ .Values.ports.routerClassifier }}
{{- end -}}
