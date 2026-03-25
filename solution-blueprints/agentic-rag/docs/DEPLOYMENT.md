<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Helm deployment
Solution Blueprints are provided as Helm Charts.

The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

An example for command-line usage:
```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external services
By default, any required AIMs (LLM, Embedding, ChromaDB) are deployed by the helm chart. If you already have compatible services deployed, you can use them instead and reuse resources.

To use an existing deployment, set the `existingService` value for the respective component. You should use the Kubernetes Service name (and port where required — see the per-service notes below), or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

### External LLM

Set `llm.existingService` to the endpoint:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  --set llm.existingService=$servicename \
  | kubectl apply -f - -n $namespace
```

### External Embedding Service

Set `embedding.existingService` to the endpoint. The port must be included because the embedding service runs on a non-standard port (default: `7997`):
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  --set embedding.existingService="my-embedding-service:7997" \
  | kubectl apply -f - -n $namespace
```

### External ChromaDB

Set `chromadb.existingService` to the endpoint. The port must be included because ChromaDB runs on a non-standard port (default: `8000`):
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  --set chromadb.existingService="my-chromadb-service:8000" \
  | kubectl apply -f - -n $namespace
```

You can combine these flags as needed.

## Default AIM image and GPU compatibility

By default, the chart deploys GPT-OSS 20B with this AIM: `amdenterpriseai/aim-openai-gpt-oss-20b:0.10.0`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  --set llm.image=amdenterpriseai/aim-openai-gpt-oss-20b:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding

To connect to the UI, port-forward port 7860. The UI will then be available at <http://localhost:7860>.

```bash
kubectl port-forward services/aimsb-agentic-rag-$name-agent-app 7860:80 -n $namespace
```

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-rag \
  --set llm.existingService=$servicename \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
```bash
echo "https://aimsb-agentic-rag-$name-agent-app$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```
