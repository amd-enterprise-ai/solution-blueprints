# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

{{- define "aim-llm.main" -}}
{{ if not .existingService -}}
{{ include "aim-llm.deployment" . }}
---
{{ include "aim-llm.service" . }}
{{- end -}}
{{- end -}}

{{- define "aim-llm.url" -}}
{{ if not .existingService -}}
http://{{ include "aim-llm.release.fullname" . }}/v1
{{- else -}}
{{ if hasPrefix .existingService "http" }}
{{ .existingService }}/v1
{{- else -}}
http://{{ .existingService }}/v1
{{- end -}}
{{- end -}}
{{- end -}}
