<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Report Generation Engine Deployment Guide

Solution Blueprints are provided as Helm Charts. The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

This blueprint supports **AMD Instinct** (default), **AMD Radeon**  and **AMD EPYC** platforms. Unless otherwise specified, the commands below cover the default **Instinct** deployment. For the other platforms, see:

- [Deploy on AMD Radeon](#amd-radeon-gpu)
- [Deploy on AMD EPYC](#amd-epyc-cpu)

## Multi-platform Support

The chart ships defaults for three platforms, selected with `--set global.platform=<platform>`: `instinct` (GPU, the default), `epyc` (CPU), and `radeon` (GPU). Each sets a matching AIM image and resource profile; inspect them with `helm show values . --jsonpath '{.llm.platformDefaults}'`.

> **Helm note**: Built and tested on Helm 3.17 or higher. On Helm v4, if the piped `kubectl apply` is rejected, run `helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine --untar` first and template the local `./aimsb-report-generation-engine` directory instead.

### AMD Instinct (GPU, default)

To deploy the blueprint, run the following command:
```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  | kubectl apply -f - -n $namespace
```

### AMD EPYC (CPU)

EPYC runs the model on CPU (`gpus=0`, `bf16`, `AIM_ALLOW_UNOPTIMIZED=true`), sized via `llm.cpus`/`llm.memory`. The default EPYC AIM is a **gated** image, so provide a Hugging Face token through a Secret.

```bash
name="my-deployment"
namespace="my-namespace"
kubectl create namespace $namespace
kubectl create secret generic hf-token --from-literal=hf-token=<YOUR_HF_TOKEN> -n $namespace

helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine --untar
helm template $name ./aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set global.platform=epyc \
  --set llm.cpus=188 \
  --set llm.memory=128 \
  --set llm.env_vars.HF_TOKEN.name=hf-token \
  --set llm.env_vars.HF_TOKEN.key=hf-token \
  | kubectl apply -f - -n $namespace
```

> **Performance note**: On multi-socket EPYC nodes, configure the kubelet for NUMA alignment (CPU Manager `static`, Topology Manager `single-numa-node`, Memory Manager `Static`); otherwise the LLM's CPUs and memory can land on different NUMA nodes and vLLM runs effectively single-threaded.

### AMD Radeon (GPU)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

## Configuration Options

All configuration is passed via `--set` flags:

| Helm Value | Default | Description |
|------------|---------|-------------|
| `config.tavily.apiKey` | `""` | **Required** - Tavily API key for web search |
| `config.llm.temperature` | `0.6` | Generation temperature (0.0-1.0) |
| `config.llm.maxRetries` | `3` | Retry attempts for structured output |
| `config.search.numberOfQueries` | `2` | Search queries per section |
| `config.search.tavilyTopic` | `general` | Search type (`general` or `news`) |
| `config.search.tavilyMaxResults` | `5` | Max results per query |
| `config.generation.maxSectionLength` | `1000` | Max words per section |
| `config.generation.finalSectionLength` | `300` | Max words for intro/conclusion |
| `llm.cpu_per_gpu` | `1` | CPU cores per GPU for LLM |


### Example with Custom Configuration

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set config.llm.temperature=0.7 \
  --set config.search.numberOfQueries=3 \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external services

By default, any required AIMs are deployed by the helm chart. If you already have compatible services deployed, you can use them instead and reuse resources.

To use an existing deployment, set the `existingService` value for the respective component. You should use the Kubernetes Service name (and port where required - see the per-service notes below), or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

### External LLM
Set `llm.existingService` to the endpoint:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set llm.existingService=$servicename \
  | kubectl apply -f - -n $namespace
```

### API Key and Model Configuration for External LLM

When using an external LLM service, you can optionally configure the API authentication credentials and specify a particular model:

- `llm.apiKey` (optional): Bearer token for API authentication
- `llm.model` (optional): The specific model identifier to use (e.g., `openai/gpt-oss-20b`, `gpt-4-turbo`)

Specifying the model is not needed when using AIMs, as the instance typically only serves one model. If `llm.model` is left empty, the list of models is queried from the API, and the first available model is used.

Example command:

```bash
name="my-deployment"
namespace="my-namespace"
api_url="https://llm-api.example.com"
api_key="<YOUR_API_KEY>"
model_name="openai/gpt-oss-20b"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set llm.existingService=$api_url \
  --set llm.apiKey=$api_key \
  --set llm.model=$model_name \
  | kubectl apply -f - -n $namespace
```

### Using Kubernetes Secrets for API Key

For enhanced security, you can store the API key in a Kubernetes secret and reference it:

```bash
name="my-deployment"
namespace="my-namespace"
secretname="my-secretname"
api_url="https://llm-api.example.com"

# Create the secret
kubectl create secret generic $secretname -n $namespace \
  --from-literal=api-key="<YOUR_API_KEY>"

# Deploy with secret reference
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set llm.existingService=$api_url \
  --set llm.apiKeySecretRef.name=$secretname \
  --set llm.apiKeySecretRef.key=api-key \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and GPU compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM: `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding
To connect to the UI, port-forward port 8501. The UI will then be available at <http://localhost:8501>.
```bash
# Port forward to access the UI
kubectl port-forward services/aimsb-report-generation-engine-$name 8501:8501 -n $namespace
```

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `envoy-gateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
```bash
echo "https://aimsb-report-generation-engine-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```

## Clean Up

When you are finished, remove the deployed resources:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  | kubectl delete -f - -n $namespace
```
