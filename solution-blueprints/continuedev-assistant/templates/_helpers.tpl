# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Base URL helper
{{- define "httpRoute.baseUrl" -}}
{{- $projectId := default "project_id" .Values.metadata.project_id -}}
{{- $userId := default "user_id" .Values.metadata.user_id -}}
{{- $workloadId := default (include "release.fullname" .) .Values.metadata.workload_id -}}
{{- printf "/%s/%s/%s" $projectId $userId $workloadId }}
{{- end -}}

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
- name: BASE_URL
  value: {{ include "httpRoute.baseUrl" . | quote }}
- name: AIM_BASE_URL
  {{/*
    Build a context that has the right .Values, .Release, and .Chart metadata.
    NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
  */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.chatLLM)
        "Release" .Release
        "Chart" (dict "Name" "chatLLM")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}
- name: AIM_AUTOCOMPLETE_BASE_URL
  {{/*
    Build a context that has the right .Values, .Release, and .Chart metadata.
    NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
  */}}
  {{- $sub := dict
        "Values" (merge (dict) .Values.autocompleteLLM)
        "Release" .Release
        "Chart" (dict "Name" "autocompleteLLM")
  -}}
  value: {{ include "aimchart-llm.url" $sub }}
{{- end -}}

# Container volume mounts helper
{{- define "container.volumeMounts" -}}
- mountPath: /workload
  name: ephemeral-storage
- mountPath: /workload/mount
  name: workload-mount
- mountPath: /dev/shm
  name: dshm
{{- if .Values.persistent_storage.enabled }}
{{- range $key, $value := .Values.persistent_storage.volumes }}
- mountPath: {{ tpl $value.mount_path $ }}
  name: {{ $key }}
{{- end }}
{{- end }}
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
- configMap:
    name: {{ include "release.fullname" . }}
  name: workload-mount
{{- if .Values.persistent_storage.enabled }}
{{- range $key, $value := .Values.persistent_storage.volumes }}
- persistentVolumeClaim:
    claimName: {{ tpl $value.pvc_name $ }}
  name: {{ $key }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "entrypoint" -}}
curl -fsSL https://code-server.dev/install.sh | sh
mkdir -p /root/.local/share/code-server/User/
cp /workload/mount/default_settings.json /root/.local/share/code-server/User/settings.json
code-server --install-extension ms-python.python
code-server --install-extension Continue.continue
code-server --install-extension GitHub.vscode-pull-request-github
code-server --install-extension ms-kubernetes-tools.vscode-kubernetes-tools
pip install requests

MODEL_NAME=$(python << 'EOF'
import os
import sys
import time
import requests
import urllib.parse
for retry in range(120):
    if retry != 0:
        print("Couldn't retrieve model name - AIM probably not up yet. Waiting 10 seconds...", file=sys.stderr)
        time.sleep(10)
    print(f"Trying to retrieve model name (attempt {retry+1})", file=sys.stderr)
    try:
        r = requests.get(urllib.parse.urljoin(os.getenv("AIM_BASE_URL"), "v1/models"), timeout=0.5)
        if r.status_code == 200:
            try:
                print(r.json()["data"][0]["id"], end="")
                break
            except (KeyError, IndexError):
                pass
    except requests.exceptions.ConnectionError:
        pass
else:
    raise RuntimeError("Failed to retrieve model name")
EOF
)
echo "Model name retrieved successfully, got: $MODEL_NAME"

{{ if .Values.autocomplete.enabled }}
AUTOCOMPLETE_MODEL_NAME=$(python << 'EOF'
import os
import sys
import time
import requests
import urllib.parse
for retry in range(120):
    if retry != 0:
        print("Couldn't retrieve model name - AIM probably not up yet. Waiting 10 seconds...", file=sys.stderr)
        time.sleep(10)
    print(f"Trying to retrieve autocomplete model name (attempt {retry+1})", file=sys.stderr)
    try:
        r = requests.get(urllib.parse.urljoin(os.getenv("AIM_AUTOCOMPLETE_BASE_URL"), "v1/models"), timeout=0.5)
        if r.status_code == 200:
            try:
                print(r.json()["data"][0]["id"], end="")
                break
            except (KeyError, IndexError):
                pass
    except requests.exceptions.ConnectionError:
        pass
else:
    raise RuntimeError("Failed to retrieve model name")
EOF
)
echo "Autocomplete model name retrieved successfully, got: $AUTOCOMPLETE_MODEL_NAME"
{{ end }}

# Create config.yaml for Continue (overwrite if exists)
mkdir -p /root/.continue
cat > /root/.continue/config.yaml << EOF
name: Local Agent
version: 1.0.1
schema: v1
models:
  - name: ${MODEL_NAME}
    provider: openai
    model: ${MODEL_NAME}
    apiKey: none
    apiBase: ${AIM_BASE_URL}
    defaultCompletionOptions:
{{ toYaml .Values.chat.defaultCompletionOptions | indent 6 }}
  {{- if .Values.autocomplete.enabled }}
  - name: ${AUTOCOMPLETE_MODEL_NAME} for Autocomplete
    provider: openai
    model: ${AUTOCOMPLETE_MODEL_NAME}
    apiKey: none
    apiBase: ${AIM_AUTOCOMPLETE_BASE_URL}
    roles:
      - autocomplete
    defaultCompletionOptions:
{{ toYaml .Values.autocomplete.defaultCompletionOptions | indent 6 }}
    autocompleteOptions:
{{ toYaml .Values.autocomplete.autocompleteOptions | indent 6 }}

  {{- end }}
context:
  - provider: file      # Reference any file in workspace
  - provider: tree      # Reference directory structure
  - provider: open      # Reference all open files
EOF

code-server --auth none --bind-addr 0.0.0.0:8080
{{- end -}}
