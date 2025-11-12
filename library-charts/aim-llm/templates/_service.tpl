# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{ define "aim-llm.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "aim-llm.release.fullname" . }}
  labels:
    app: {{ include "aim-llm.release.fullname" . }}
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: {{ default 8000 (index (default dict .env_vars) "AIM_PORT" ) }}
  selector:
    app: {{ include "aim-llm.release.fullname" . }}
{{- end }}
