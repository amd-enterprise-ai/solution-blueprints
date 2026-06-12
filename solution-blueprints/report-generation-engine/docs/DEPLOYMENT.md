<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Deployment Guide - AMD Report Generation Engine

Deploy the Report Generation Engine Solution Blueprint from the container registry using Helm.

## Prerequisites

- Kubernetes cluster with `kubectl` access
- Helm 3.x installed
- Tavily API key (https://tavily.com - free tier: 1,000 requests/month)

---

## Quick Deploy

Deploys with the default LLM (Llama-3.3-70B):

```bash
name="rge"
namespace="rge"

# Create namespace
kubectl create namespace $namespace

# Deploy (includes LLM)
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  | kubectl apply -f - -n $namespace
```

### Use Existing LLM Service

If you already have an LLM running in your cluster:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set llm.existingService=my-llm.namespace.svc.cluster.local \
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
name="rge"
namespace="rge"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

---

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
| `llm.image` | `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1` | AIM image to deploy (if not using existing service) |
| `llm.existingService` | `""` | Use existing LLM service (skips LLM deployment) |
| `llm.cpu_per_gpu` | `1` | CPU cores per GPU for LLM |

### LLM Configuration

Choose ONE of these options:

1. **Use existing LLM service**: Set `llm.existingService` to point to a running LLM
2. **Deploy new LLM**: Set `llm.image` to an AIM image from the [AIM catalog](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html)

> **Note**: The LLM model is auto-discovered from the vLLM service's `/v1/models` endpoint.

> **Resource tip**: If your cluster has limited CPU, you can adjust CPU cores per GPU using `--set llm.cpu_per_gpu=<value>` (default: 1).

### Example with Custom Configuration

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set config.llm.temperature=0.7 \
  --set config.search.numberOfQueries=3 \
  --set llm.existingService=$llm_service \
  | kubectl apply -f - -n $namespace
```

---

## Access the Application

### Option 1: Port Forwarding

```bash
# Port forward to access the UI
kubectl port-forward services/aimsb-report-generation-engine-$name 8501:8501 -n $namespace
```

Open http://localhost:8501 in your browser.
---

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
name="rge"
namespace="rge"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  --set config.tavily.apiKey=tvly-your-key-here \
  --set llm.existingService=my-llm.namespace.svc.cluster.local \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
   ```bash
   echo "https://aimsb-report-generation-engine-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
   ```

## Verify Deployment

```bash
# Check pods are running
kubectl get pods -n $namespace

# Check service
kubectl get svc -n $namespace

# View logs
kubectl logs deployment/aimsb-report-generation-engine-$name -n $namespace --tail=50
```

---

## Uninstall

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-report-generation-engine \
  | kubectl delete -f - -n $namespace
```

---
