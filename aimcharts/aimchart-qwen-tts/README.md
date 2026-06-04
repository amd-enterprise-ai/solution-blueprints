<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIM Qwen TTS Chart

This chart deploys Qwen3 TTS (`vllm --omni`) on Kubernetes.

The chart has some functionality designed for use as a subchart:
- The chart defines an `aimchart-qwen-tts.url` template function which can be used in parent chart templates to determine the URL to connect to the deployment.
- The chart accepts an `existingService: ...` key which overrides the deployment and instead uses the existing one.

## Configuration

Key configurable values:

| Parameter | Description | Default |
|---|---|---|
| `image` | Container image | `vllm/vllm-omni-rocm:0.14.0` |
| `model` | HuggingFace model to serve | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` |
| `extraArgs` | Additional arguments passed to `vllm serve` | See `values.yaml` |
| `replicas` | Number of pod replicas | `1` |
| `gpus` | Number of AMD GPUs per pod | `1` |
| `resources.requests.cpu` / `resources.limits.cpu` | CPU resources | `2` / `4` |
| `resources.requests.memory` / `resources.limits.memory` | Memory resources | `8Gi` / `16Gi` |
| `service.targetPort` | Container port for vllm serve | `8091` (template default) |
| `existingService` | Use an existing service instead of deploying | `null` |

The service type is always `ClusterIP` with port `80`, forwarding to `service.targetPort` (defaults to `8091`).

The chart constructs the command `vllm serve <model> --port <service.targetPort> <extraArgs...>`, so you only need to provide model-specific flags via `extraArgs`.

## Deploying

To deploy from this directory, pipe the output from `helm template` to `kubectl apply`.
Replace the variables with whatever is appropriate to you, and run:

```bash
name=my-qwen-tts-deployment
namespace=my-namespace
helm template $name . \
    | kubectl apply -f - -n $namespace
```

To override the default model:
```bash
helm template $name . \
  --set model=Qwen/Qwen3-TTS-12Hz-1.7B-Base \
    | kubectl apply -f - -n $namespace
```

Or with a custom values file:

```yaml
model: "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
extraArgs:
  - --trust-remote-code
  - --enforce-eager
```

```bash
helm template $name . -f custom-values.yaml | kubectl apply -f - -n $namespace
```

### Connecting, testing

It may take a while for the TTS service to be ready to accept requests (model download on first launch). The chart includes a startup probe that allows up to ~60 minutes for initialization (360 checks every 10 seconds). Wait until the deployment shows READY:
```bash
kubectl get deployment.apps/aimchart-qwen-tts-$name -n $namespace
```

To connect to the service, start a port-forward.
```bash
kubectl port-forward services/aimchart-qwen-tts-$name 8091:80 -n $namespace
```

Then test the deployment:
```bash
curl http://localhost:8091/health
```
which should print a successful health response.

## How to use this application chart as a dependency

Add the chart as a dependency in your chart's Chart.yaml:
```yaml
dependencies:
- name: aimchart-qwen-tts
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: qwen-tts
```

With this alias, your values file should have a section of `.Values.qwen-tts` which can match the `values.yaml` of this chart:
```yaml
qwen-tts:
  existingService: null

  nameOverride: null
  fullnameOverride: null
  metadata:
    labels: {}
    project_id: project
    user_id: user
    workload_id: # defaults to the release name

  image: "vllm/vllm-omni-rocm:0.14.0"
  model: "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
  replicas: 1

  gpus: 1
  resources:
    requests:
      cpu: "2"
      memory: "8Gi"
    limits:
      cpu: "4"
      memory: "16Gi"

  securityContext: {}
  service: {}
```

If you need to include multiple TTS services, add the dependency multiple times with different aliases, for example:

```yaml
dependencies:
- name: aimchart-qwen-tts
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: primary-tts
- name: aimchart-qwen-tts
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: backup-tts
```

and then have values.yaml sections for each:
```yaml
primary-tts:
  model: "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

backup-tts:
  model: "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
```

### URL template function

In your chart, to get the URL of the TTS service, use the `aimchart-qwen-tts.url` template function.
You need to call it with a context constructed as follows:
```yaml
{{/*
  Build a context that has the right .Values, .Release, and .Chart metadata.
  NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
*/}}
{{- $sub := dict
      "Values" (merge (dict) .Values.qwen-tts)
      "Release" .Release
      "Chart" (dict "Name" "qwen-tts")
-}}
url: {{ include "aimchart-qwen-tts.url" $sub }}
```
If you use multiple dependencies, make sure to use the correct keys, e.g. `"Values" (merge (dict) .Values.primary-tts)` and `"Chart" (dict "Name" "primary-tts")`.
