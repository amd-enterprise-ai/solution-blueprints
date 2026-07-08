<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Embedding Chart

This chart deploys a vLLM-based OpenAI-compatible embedding server.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| image | string | "amdenterpriseai/aim-base:0.11" | Image repository and tag |
| model | string | "intfloat/multilingual-e5-large-instruct" | Embedding model to use |
| gpus | int | 0 | Number of GPUs to request |


### Platforms

The chart provides defaults for running on both Instinct (default) and Epyc.
To select a platform use

```bash
name=my-llm-deployment
namespace=my-namespace
helm template $name . \
  --set platform=<platform> \
    | kubectl apply -f - -n $namespace
```

where `<platform>` can be either `instinct` or `epyc`.

The platform can also be selected via the global value `global.platform`

```bash
--set global.platform=<platform>
```

which can be useful when using this chart as a dependency of another graph.
Note that `platform` takes precedence over `global.platform`.
If neither `platform` nor `global.platform` are set, the chart defaults to the `instinct`
platform.

To override a default value, just pass the overriding value explicitly, e.g. to use `meta-llama/Llama-3.2-1B-Instruct` on Epyc

```bash
--set platform=epyc --set image=docker.io/amdenterpriseai/aim-epyc-meta-llama-llama-3-2-1b-instruct:0.11.0-preview
```

You can inspect the default platform value with

```bash
helm show values . --jsonpath '{.platformDefaults}'
```
