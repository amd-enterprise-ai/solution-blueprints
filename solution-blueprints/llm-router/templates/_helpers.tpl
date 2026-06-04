# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "router.complexName" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
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

{{- define "llm.modelApiKeySecretName" -}}
{{- $model := .model -}}
{{- $secretRef := default $model.apiKeySecretRef $model.api_key_secret_ref -}}
{{- if and (kindIs "map" $secretRef) (hasKey $secretRef "name") -}}
{{- default "" $secretRef.name | trim -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "llm.modelApiKeySecretKey" -}}
{{- $model := .model -}}
{{- $secretRef := default $model.apiKeySecretRef $model.api_key_secret_ref -}}
{{- if and (kindIs "map" $secretRef) (hasKey $secretRef "key") -}}
{{- default "" $secretRef.key | trim -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "llm.modelApiKeyEnvVar" -}}
{{- $model := .model -}}
{{- printf "LLM_API_KEY_%s" (regexReplaceAll "[^A-Za-z0-9]" (upper $model.name) "_") -}}
{{- end -}}

{{- define "llm.backendApiKeySecretName" -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- include "llm.modelApiKeySecretName" (dict "model" $model "Values" .Values) -}}
{{- end -}}

{{- define "llm.backendApiKeySecretKey" -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- include "llm.modelApiKeySecretKey" (dict "model" $model "Values" .Values) -}}
{{- end -}}

{{- define "llm.backendApiKeyEnvVar" -}}
{{- $model := (include "llm.findModel" . | fromYaml) -}}
{{- $secretName := include "llm.modelApiKeySecretName" (dict "model" $model "Values" .Values) | trim -}}
{{- $secretKey := include "llm.modelApiKeySecretKey" (dict "model" $model "Values" .Values) | trim -}}
{{- if and $secretName $secretKey -}}
{{- include "llm.modelApiKeyEnvVar" (dict "model" $model) -}}
{{- else -}}
{{- "" -}}
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

{{- define "embedding.url" -}}
 http://{{ .Release.Name }}-embedding:{{ .Values.embedding.deployment.ports.http }}
{{- end -}}
