<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIM LLM Chart

This chart deploys AMD Inference Microservice LLMs.

The chart has some functionality designed for use as a subchart, a dependency in a larger application such as an AMD Solution Blueprint:
- The chart defines an `aimchart-llm.url` template function which can be used in parent chart templates to determine the URL to connect to the deployment.
- The chart accepts an `existingService: ...` key which overrides the deployment and instead uses the existing one.


## Deploying

First choose the model to deploy. Usually this is done by choosing the corresponding image from https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html.
Then to deploy an AIM from this directory, pipe the output from `helm template` to `kubectl apply`.
Replace the variables with whatever is appropriate to you, and run:
```bash
name=my-llm-deployment
namespace=my-namespace
image="docker.io/amdenterpriseai/my-chosen-model"
helm template $name . \
  --set image=$image \
    | kubectl apply -f - -n $namespace
```

### Connecting, testing
It may take a while for an LLM to be ready to accept requests, wait until the deployment shows READY:
```bash
kubectl get deployment.apps/aimchart-llm-$name -n$namespace
```

To connect to the LLM, start a port-forward.
```bash
kubectl port-forward services/aimchart-llm-$name 8080:80 -n $namespace
```

Then test the deployment:
```bash
question="I'm testing the connection. Is the LLM receiving?"
curl http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -X POST \
    -d '{
        "messages": [
            {"role": "user", "content": "'"$question"'"}
        ]
    }' \
  | jq .
```
which should print a JSON formatted response.

### Using a custom profile

You can embed custom profiles, which are YAML files, in the values overrides. Specify for example:

```yaml
customProfiles:
  vllm-mi300x-fp8-tp1-latency-no-async-scheduling.yaml:
    aim_id: meta-llama/Llama-3.1-8B-Instruct
    model_id: amd/Llama-3.1-8B-Instruct-FP8-KV
    metadata:
      engine: vllm
      gpu: MI300X
      precision: fp8
      gpu_count: 1
      metric: latency
      manual_selection_only: false
      type: optimized
    engine_args:
      swap-space: 64
      tensor-parallel-size: 1
      max-num-seqs: 512
      kv-cache-dtype: fp8
      max-seq-len-to-capture: 32768
      max-num-batched-tokens: 1024
      max-model-len: 32768
      no-enable-prefix-caching:
      no-enable-log-requests:
      disable-uvicorn-access-log:
      no-trust-remote-code:
      gpu-memory-utilization: 0.9
      distributed_executor_backend: mp
      no-async-scheduling:
    env_vars:
      GPU_ARCHS: "gfx942"
      HSA_NO_SCRATCH_RECLAIM: "1"
      VLLM_USE_AITER_TRITON_ROPE: "1"
      VLLM_ROCM_USE_AITER: "1"
      VLLM_ROCM_USE_AITER_RMSNORM: "1"
```
The top key is the filename, so this profile will be mounted in to the AIM as a `vllm-mi300x-fp8-tp1-latency-no-async-scheduling.yaml`. You can include as many custom profiles as you wish.

To select a particular custom profile, you can set the `AIM_PROFILE_ID` environment variable. Here's how to build the profile id:
- For custom general profiles: `custom/general/<profile_name>`
- For custom model-specific profiles: `custom/<org>/<model>/<profile_name>`
where `<profile_name>` is the filename without the `.yaml` suffix. Thus to force the choice of the above example profile, you would set:

```yaml
env_vars:
  AIM_PROFILE_ID: custom/meta-llama/Llama-3.1-8B-Instruct/vllm-mi300x-fp8-tp1-latency-no-async-scheduling
```

## How to use this application chart as a dependency

Add the chart as a dependency in your chart's Chart.yaml:
```yaml
dependencies:
- name: aimchart-llm
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: llm
```

With this alias, your values file should have a section of `.Values.llm` which can match the `values.yaml` of this chart:
```yaml
llm:
  existingService: null  # Specify this to override the whole implementation, and use an existing service instead

  nameOverride: null
  fullnameOverride: null
  metadata:
    labels: {}
    project_id: silogen
    user_id: user
    workload_id: # defaults to the release name

  image: "amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:0.8.5"
  replicas: 1

  gpus: 1
  memory_per_gpu: 64 # Gi
  cpu_per_gpu: 4

  env_vars:
    # You could use any AIM environment variables, e.g.
    # AIM_PRECISION: "fp8"

    # You may provide a HuggingFace token that's stored in a Secret called `hf-token` in the key `hf-token` by adding:
    # HF_TOKEN:
    #   key: hf-token
    #   name: hf-token

  storage:
    ephemeral:
      quantity: 256Gi
      # Omit storageClassName and accessModes to fall back to ephemeral storage
      storageClassName: mlstorage
      accessModes:
        - ReadWriteOnce
    dshm:
      sizeLimit: 32Gi
```

If you need to include multiple LLMs, add the dependency multiple times with different aliases, for example:

```yaml
dependencies:
- name: aimchart-llm
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: agent-llm
- name: aimchart-llm
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
  alias: autocomplete-llm
```

and then have values.yaml sections for each:
```yaml
agent-llm:
  image: "registry-1.docker.io/amdenterpriseai/aim:a.b.c-example-model-3-70b-instruct"

autocomplete-llm:
  image: "registry-1.docker.io/amdenterpriseai/aim:x.y.z-example-model-3-8b"
```

### URL template function

In your chart, to get the url of the LLM, use the `aimchart-llm.url` template function.
You need to call it with a context constructed as follows:
```yaml
{{/*
  Build a context that has the right .Values, .Release, and .Chart metadata.
  NOTE that .Chart.Name should be the same as given to alias in the dependencies list.
*/}}
{{- $sub := dict
      "Values" (merge (dict) .Values.llm)
      "Release" .Release
      "Chart" (dict "Name" "llm")
-}}
url: {{ include "aimchart-llm.url" $sub }}
```
If you use multiple dependencies, make sure to use the correct keys, e.g. `"Values" (merge (dict) .Values.autocomplete-llm)` and `"Chart" (dict "Name" "autocomplete-llm")`.
