<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIM Qwen ASR Chart

This chart deploys a Qwen3 ASR service based on vLLM.

The chart has some functionality designed for use as a subchart, a dependency in a larger application:
- The chart defines an `aimchart-qwen-asr.url` template function which can be used in parent chart templates to determine the URL to connect to the deployment.
- The chart accepts an `existingService: ...` key which overrides the deployment and instead uses the existing one.

## Configuration

The startup script (dependency installation, vLLM launch) is baked into the deployment template and is not configurable via values.

Key configurable values:

| Parameter | Description | Default |
|---|---|---|
| `image` | Container image | `rocm/vllm:v0.14.0_amd_dev` |
| `model` | HuggingFace model to serve | `Qwen/Qwen3-ASR-1.7B` |
| `replicas` | Number of pod replicas | `1` |
| `gpus` | Number of AMD GPUs per pod | `1` |
| `memory.requests` / `memory.limits` | Memory resources | `32Gi` / `64Gi` |
| `cpu.requests` / `cpu.limits` | CPU resources | `4` / `8` |
| `existingService` | Use an existing service instead of deploying | `null` |

## Deploying

To deploy from this directory, pipe the output from `helm template` to `kubectl apply`.
Replace the variables with whatever is appropriate to you, and run:

```bash
name=my-qwen-asr-deployment
namespace=my-namespace
helm template $name . \
    | kubectl apply -f - -n $namespace
```

To override the default model:
```bash
helm template $name . \
  --set model=Qwen/Qwen3-ASR-1.7B \
    | kubectl apply -f - -n $namespace
```

### Connecting, testing
It may take a while for the ASR service to be ready to accept requests (the startup script installs dependencies and downloads the model on first launch — up to ~20 minutes). Wait until the deployment shows READY:
```bash
kubectl get deployment.apps/aimchart-qwen-asr-$name -n $namespace
```

To connect to the service, start a port-forward.
```bash
kubectl port-forward services/aimchart-qwen-asr-$name 8080:80 -n $namespace
```

Then test the deployment:
```bash
curl http://localhost:8080/health
```
which should print a successful health response.

## How to use this application chart as a dependency

Add the chart as a dependency in your chart's Chart.yaml:
```yaml
dependencies:
- name: aimchart-qwen-asr
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: qwen-asr
```

With this alias, your values file should have a section of `.Values.qwen-asr` which can match the `values.yaml` of this chart:
```yaml
qwen-asr:
  existingService: null

  nameOverride: null
  fullnameOverride: null
  metadata:
    labels: {}
    project_id: project
    user_id: user
    workload_id: # defaults to the release name

  model: "Qwen/Qwen3-ASR-1.7B"
  imagePullPolicy: Always
  replicas: 1

  gpus: 1
  memory:
    requests: 32Gi
    limits: 64Gi
  cpu:
    requests: "4"
    limits: "8"

  service:
    type: ClusterIP
    port: 80
    targetPort: 8000
```

If you need to include multiple ASR services, add the dependency multiple times with different aliases, for example:

```yaml
dependencies:
- name: aimchart-qwen-asr
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: transcription-asr
- name: aimchart-qwen-asr
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: backup-asr
```

and then have values.yaml sections for each:
```yaml
transcription-asr:
  model: "Qwen/Qwen3-ASR-1.7B"

backup-asr:
  model: "Qwen/Qwen3-ASR-0.6B"
```

### URL template function

In your chart, to get the URL of the ASR service, use the `aimchart-qwen-asr.url` template function.
You need to call it with a context constructed as follows:
```yaml
{{/*
  Build a context that has the right .Values, .Release, and .Chart metadata.
  NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
*/}}
{{- $sub := dict
      "Values" (merge (dict) .Values.qwen-asr)
      "Release" .Release
      "Chart" (dict "Name" "qwen-asr")
-}}
url: {{ include "aimchart-qwen-asr.url" $sub }}
```
If you use multiple dependencies, make sure to use the correct keys, e.g. `"Values" (merge (dict) .Values.transcription-asr)` and `"Chart" (dict "Name" "transcription-asr")`.
