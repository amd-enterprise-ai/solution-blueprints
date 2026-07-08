<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Talk to Your Documents Deployment Guide

Solution Blueprints are provided as Helm Charts. The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

This blueprint supports **AMD Instinct** (default), **AMD EPYC**, and **AMD Radeon** platforms. Unless otherwise specified, the commands below cover the default **Instinct** deployment. For the other platforms, see:

- [Deploy on AMD EPYC](#amd-epyc-cpu)
- [Deploy on AMD Radeon](#amd-radeon-gpu)

## Multi-platform Support

The chart ships defaults for three platforms, selected with `--set global.platform=<platform>`: `instinct` (GPU, the default), `epyc` (CPU), and `radeon` (GPU). Each sets matching AIM images and resource profiles for the LLM and embedding components; inspect them with `helm show values . --jsonpath '{.llm.platformDefaults}'` and `helm show values . --jsonpath '{.embedding.platformDefaults}'`.

> **Helm note**: Built and tested on Helm 3.17 or higher. On Helm v4, if the piped `kubectl apply` is rejected, run `helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents --untar` first and template the local `./aimsb-talk-to-your-documents` directory instead.

### AMD Instinct (GPU, default)

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  | kubectl apply -f - -n $namespace
```

### AMD EPYC (CPU)

EPYC runs the LLM on CPU (`gpus=0`, `bf16`, `AIM_ALLOW_UNOPTIMIZED=true`), sized via `llm.cpus`/`llm.memory`. The embedding service runs separately on CPU (`aim-epyc-base` serving `intfloat/multilingual-e5-small`), sized via `embedding.resources`. `global.platform=epyc` selects EPYC defaults for both components. The default EPYC AIM images are **gated**, so provide a Hugging Face token through a Secret.

```bash
name="my-deployment"
namespace="my-namespace"
kubectl create namespace $namespace
kubectl create secret generic hf-token --from-literal=hf-token=<YOUR_HF_TOKEN> -n $namespace

helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents --untar
helm template $name ./aimsb-talk-to-your-documents \
  --set global.platform=epyc \
  --set llm.cpus=188 \
  --set llm.memory=128 \
  --set llm.env_vars.HF_TOKEN.name=hf-token \
  --set llm.env_vars.HF_TOKEN.key=hf-token \
  --set embedding.env_vars.HF_TOKEN.name=hf-token \
  --set embedding.env_vars.HF_TOKEN.key=hf-token \
  | kubectl apply -f - -n $namespace
```

> **Resource sizing note**: Depending on your node it may be necessary to resize the LLM and embedding model resources. For example, the following parameters can be set to limit the embedding model's cpu count and memory:
> ```bash
> --set embedding.resources.requests.cpu=32 --set embedding.resources.limits.cpu=32 \
> --set embedding.resources.requests.memory=32Gi --set embedding.resources.limits.memory=32Gi \
> ```

> **Performance note**: On multi-socket EPYC nodes, configure the kubelet for NUMA alignment (CPU Manager `static`, Topology Manager `single-numa-node`, Memory Manager `Static`); otherwise the LLM's and embedding service's CPUs and memory can land on different NUMA nodes and vLLM runs effectively single-threaded.

### AMD Radeon (GPU)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external services

By default, any required AIMs (LLM, Embedding, ChromaDB) are deployed by the helm chart. If you already have compatible services deployed, you can use them instead, and reuse resources.

To use an existing deployment, set the `existingService` value for the respective component. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

### External LLM

Set `llm.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set llm.existingService="http://my-llm-service:8000" \
  | kubectl apply -f - -n $namespace
```

### External Embedding Service

Set `embedding.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set embedding.existingService="http://my-embedding-service:7997" \
  | kubectl apply -f - -n $namespace
```

### External ChromaDB

Set `chromadb.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set chromadb.existingService="http://my-chromadb-service:8000" \
  | kubectl apply -f - -n $namespace
```

You can combine these flags as needed.

### API Key and Model Configuration for External LLM

When using an external LLM service, you can optionally configure the API authentication credentials and specify a particular model:

- `llm.apiKey` (optional): Bearer token for API authentication
- `llm.model` (optional): The specific model identifier to use (e.g., `openai/gpt-oss-20b`, `gpt-4-turbo`)

If `llm.model` is left empty, the model list is queried from the API and the first available model is used.

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set llm.existingService="https://llm-api.example.com" \
  --set llm.apiKey="<YOUR_API_KEY>" \
  --set llm.model="openai/gpt-oss-20b" \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and platform compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM: `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1` for the Instinct (GPU) platform.

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

### Platform defaults

The chart provides defaults for running on Instinct (default) and Epyc.
To select a platform use `global.platform`, as

```bash
name=my-llm-deployment
namespace=my-namespace
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set global.platform=<platform> \
    | kubectl apply -f - -n $namespace
```

where `<platform>` can be either `instinct`, `epyc` or `radeon`.

Similarly as described above, you can still override any value, including the platform.
For example, to use `meta-llama/Llama-3.2-1B-Instruct` as the LLM on Epyc, but otherwise keep the Epyc defaults, use

```bash
--set global.platform=epyc --set llm.image=docker.io/amdenterpriseai/aim-epyc-meta-llama-llama-3-2-1b-instruct:0.11.0-preview
```

Or, to use `instinct` as the global (default) platform, but run the embedding model on Epyc,

```bash
--set global.platform=instinct --set embedding.platform=epyc
```

This chart uses two components that take platform-specific values - an LLM (aliased under `llm`) and an embedding model (aliased under `embedding`).
To check the default values, use

```bash
helm show values . --jsonpath '{.<alias>.platformDefaults}'
```

## Connecting

### Option 1: Port Forwarding
Then, to connect to the UI, port-forward 7860 to be able to access the UI. The UI will then be available at <http://localhost:7860>.

```bash
kubectl port-forward services/$name-aimsb-talk-to-your-documents 7860:80 -n $namespace
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
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:

```bash
echo "https://$name-aimsb-talk-to-your-documents$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```

## Clean Up

When you are finished, remove the deployed resources:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  | kubectl delete -f - -n $namespace
```
