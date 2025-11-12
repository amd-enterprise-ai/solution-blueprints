# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Release fullname helper
{{- define "release.fullname" -}}
{{- $currentTime := now | date "20060102-1504" -}}
{{- if ne .Release.Name "release-name" -}}
autogenstudio-{{ .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
autogenstudio-{{ $currentTime | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

# Container environment variables helper
{{- define "container.env" -}}
- name: OPENAI_API_BASE_URL
  value: {{ include "aim-llm.url" .Values.llm }}"
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

# Default gallery JSON template - processes template variables
{{/*
Default gallery configuration with template processing
Model names will be replaced at runtime by the entrypoint script
*/}}
{{- define "default.gallery.json" -}}
{{- $content := .Files.Get "src/default-gallery.json" -}}
{{- $content := $content | replace "{{- include \\\"aim-llm.url\\\" .Values.llm -}}" (include "aim-llm.url" .Values.llm) -}}
{{ $content }}
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

echo "[run] silently launching autogen studio to initialize the app directory and database..."
timeout 3 autogenstudio ui --appdir "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}" || true

echo "[patch] extracting model name from AIM service..."
MODEL_NAME=$(python << 'EOF'
import sys
import time
import requests
import urllib.parse
for retry in range(120):
    if retry != 0:
        wait_time = 10
        print(f"Couldn't retrieve model name - AIM probably not up yet. Waiting {wait_time} seconds...", file=sys.stderr)
        time.sleep(wait_time)
    print(f"Trying to retrieve model name (attempt {retry+1})", file=sys.stderr)
    try:
        r = requests.get(urllib.parse.urljoin({{ include "aim-llm.url" .Values.llm | quote }}, "v1/models"), timeout=0.5)
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

echo "[patch] setting MODEL_NAME environment variable for template substitution..."
export MODEL_NAME

echo "[patch] processing gallery template with environment variables..."
envsubst < /mnt/config/default-gallery.json > /tmp/default-gallery.json

echo "[patch] injecting default gallery into the database..."
sqlite-utils insert --pk id "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}/autogen04202.db" gallery /tmp/default-gallery.json --pk id --replace

echo "[run] starting AutoGen Studio..."
exec autogenstudio ui --appdir "{{ .Values.envVars.AUTOGENSTUDIO_APPDIR }}" --host 0.0.0.0 --port {{ .Values.service.port }}
{{- end -}}
