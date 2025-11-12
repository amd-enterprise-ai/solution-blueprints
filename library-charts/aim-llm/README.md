<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIM LLM Library Chart

_NOTE: In the future, we may move to Application charts rather than Library charts_

This is a [library chart](https://helm.sh/docs/topics/library_charts/).

## How to use this library chart

Add the chart as a dependency in your chart's Chart.yaml:
```yaml
dependencies:
- name: libchart-aim-llm
  version: ___ # Whichever version you want
  repository: oci://registry-1.docker.io/amdenterpriseai
```
Then in your chart, include the resources for an AIM LLM with `{{ include "aim-llm.main" .Values.llm }}`
and to connect to the LLM, you should use `{{ include "aim-llm.url" .Values.llm }}`.
There `.Values.llm` should come from a values section that something like:
```yaml
llm:
  existingService: null  # Specify this to override the whole implementation, and use an existing service instead

  nameOverride: null
  fullnameOverride: null
  metadata:
    labels: {}
    project_id: "project_id"
    user_id: "user_id"
    workload_id: # defaults to the release name

  image: "amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:0.8.4"
  replicas: 1
  # Example image pull secret:
  # imagePullSecrets:
  #   - name: regcred

  gpus: 1
  memory_per_gpu: 64 # Gi
  cpu_per_gpu: 4

  env_vars:
    # Use any available AIM Environment Variable
    #
    # To use HF_TOKEN from a secret named "hf-token" with key "hf-token", you can use:
    # HF_TOKEN:
    #   name: hf-token
    #   key: hf-token

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
