# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{ define "aim-llm.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "aim-llm.release.fullname" . }}
  labels:
    app: {{ include "aim-llm.release.fullname" . }}
    {{- $metadataBloc := .metadata | default dict }}
    {{- range $key, $value := ($metadataBloc.labels | default dict ) }}
    {{ $key }}: {{ $value | quote }}
    {{- end }}
spec:
  replicas: {{ .replicas | default 1 }}
  selector:
    matchLabels:
      app: {{ include "aim-llm.release.fullname" . }}
  template:
    metadata:
      labels:
        app: {{ include "aim-llm.release.fullname" . }}
    spec:
      {{- if .imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml .imagePullSecrets | nindent 8 }}
      {{- end }}
      containers:
        - name: aim-llm
          {{- if .env_vars }}
          env:
            {{- include "aim-llm.container.env" . | nindent 12 }}
          {{- end }}
          image: {{ .image | quote}}
          imagePullPolicy: "Always"
          ports:
            - name: http
              containerPort: {{ default 8000 (index (default dict .env_vars) "AIM_PORT" ) }}
          startupProbe:
            httpGet:
              path: /v1/models
              port: http
            periodSeconds: 10
            failureThreshold: 360 # 360 x 10s => allow for 60 minutes startup time
          livenessProbe:
            httpGet:
              path: /health
              port: http
          readinessProbe:
            httpGet:
              path: /v1/models
              port: http
          resources:
            {{- include "aim-llm.container.resources" . | nindent 12 }}
          volumeMounts:
            {{- include "aim-llm.container.volumeMounts" . | nindent 12 }}
      volumes:
  {{- include "aim-llm.container.volumes" . | nindent 8 }}
{{- end -}}
