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
{{- if .Values.llm.apiKeySecretRef }}
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.llm.apiKeySecretRef.name }}
      key: {{ .Values.llm.apiKeySecretRef.key }}
{{- else if .Values.llm.apiKey }}
- name: LLM_API_KEY
  value: {{ .Values.llm.apiKey | quote }}
{{- end }}
{{- if .Values.llm.model }}
- name: LLM_MODEL
  value: {{ .Values.llm.model | quote }}
{{- end }}
{{- range $key, $value := .Values.envVars }}
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


# AutoGen Studio entrypoint script
{{/*
AutoGen Studio application entrypoint script
Handles installation, initialization, and startup of AutoGen Studio
*/}}
{{- define "autogenstudio.entrypoint" -}}
set -eu

echo "=== AutoGen Studio ==="
python3 --version; pip --version
echo "[pip] installing AutoGen Studio..."
pip install --no-cache-dir "{{ .Values.autogenstudio.pip }}"

echo "[pip] installing sqlite-utils for database injection..."
pip install --no-cache-dir sqlite-utils

echo "[pip] installing requests for model name extraction..."
pip install --no-cache-dir requests

echo "[apt] installing gettext for envsubst (environment variable substitution)..."
apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

echo "[playwright] installing playwright and browsers for web surfing agents..."
pip install --no-cache-dir playwright
playwright install-deps
playwright install chromium

echo "[run] launching autogen studio in background to initialize the app directory and database..."
autogenstudio ui --appdir "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}" > /dev/null 2>&1 &
AUTOGEN_PID=$!
echo "[run] autogenstudio started with PID $AUTOGEN_PID, waiting for database to be created..."

DB_PATH="{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}/autogen04202.db"
for retry in $(seq 1 60); do
  if [ -f "$DB_PATH" ]; then
    echo "[run] database file created, terminating autogenstudio..."
    kill $AUTOGEN_PID 2>/dev/null || true
    wait $AUTOGEN_PID 2>/dev/null || true
    break
  fi
  sleep 1
done

if [ ! -f "$DB_PATH" ]; then
  echo "[run] database file was not created within 60 seconds, terminating autogenstudio..." >&2
  kill $AUTOGEN_PID 2>/dev/null || true
  exit 1
fi

if [ -z "${LLM_MODEL:-}" ]; then
  echo "[patch] extracting model name from AIM service..."
  MODEL_NAME=$(python << 'EOF'
import os
import sys
import time
import requests
import urllib.parse
api_key = os.environ.get("LLM_API_KEY")
headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
for retry in range(120):
    if retry != 0:
        wait_time = 10
        print(f"Couldn't retrieve model name - AIM probably not up yet. Waiting {wait_time} seconds...", file=sys.stderr)
        time.sleep(wait_time)
    print(f"Trying to retrieve model name (attempt {retry+1})", file=sys.stderr)
    try:
        r = requests.get(urllib.parse.urljoin(os.environ["OPENAI_API_BASE_URL"], "v1/models"), headers=headers, timeout=0.5)
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
else
  echo "Using provided model name from environment variable: $LLM_MODEL"
  MODEL_NAME="$LLM_MODEL"
fi

export LLM_API_KEY="${LLM_API_KEY:-none}"

echo "[patch] setting MODEL_NAME environment variable for template substitution..."
export MODEL_NAME

echo "[patch] processing gallery template with environment variables..."
envsubst < /mnt/config/default-gallery.json > /tmp/default-gallery.json

echo "[patch] injecting default gallery into the database..."
sqlite-utils insert --pk id "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}/autogen04202.db" gallery /tmp/default-gallery.json --pk id --replace

echo "[run] starting AutoGen Studio..."
exec autogenstudio ui --appdir "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}" --host 0.0.0.0 --port {{ .Values.service.port }}
{{- end -}}
