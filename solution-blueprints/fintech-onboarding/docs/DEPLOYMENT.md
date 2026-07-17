<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# FinTech Onboarding Deployment Guide

Solution Blueprints are provided as Helm Charts. The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that regular users are allowed to create.

This blueprint supports **AMD Instinct** (default) and **AMD Radeon** platforms. Unless otherwise specified, the commands below cover the default **Instinct** deployment. For deployment with Radeon, see:

- [Deploy on AMD Radeon](#amd-radeon-gpu)

## Multi-platform Support

The chart ships defaults for two platforms, selected with `--set global.platform=<platform>`: `instinct` (GPU, the default) and `radeon` (GPU). Each sets a matching AIM image and resource profile; inspect them with `helm show values . --jsonpath '{.vlm.platformDefaults}'`.

> **Helm note**: Built and tested on Helm 3.17 or higher. On Helm v4, if the piped `kubectl apply` is rejected, run `helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding --untar` first and template the local `./aimsb-fintech-onboarding` directory instead.

### AMD Instinct (GPU, default)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  | kubectl apply -f - -n $namespace
```

### AMD Radeon (GPU)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

## GPU Support (AMD ROCm)

The service requires **at least 1 AMD GPU** to run. If you don't already have a VLM deployed,
you'll need an additional GPU, for a total of **at least 2 GPUs** for this deployment.
All necessary GPU parameters are configured automatically.

## Quick Start

The sections below cover fintech-specific deployment options (with or without an existing VLM). For platform selection, see Multi-platform Support above.

There are two deployment options:

### If you don't have an existing VLM deployment

Example command to start the service:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  | kubectl apply -f - -n $namespace
```

Wait until all pods are `Ready`, then port-forward to the UI with the following command:

```bash
kubectl port-forward svc/$name-aimsb-fintech-onboarding-ui 8080:8080 -n $namespace
```

To clean up:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  | kubectl delete -f - -n $namespace
```

### If you already have a deployed VLM service

Example command to start the service:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set vlm.existingService="<my-vlm-service-ip-address>:8000" \
  | kubectl apply -f - -n $namespace
```

**Important notes about the `vlm.existingService` parameter:**

- `vlm.existingService` is **only the base address of the model service**, without API path suffix
  `/v1` and without `http://` prefix.
  Correct examples:
    - `<my-vlm-service-ip-address>:8000`
    - `mistralai-small-24B-Instruct`
    - `my-model.default.svc.cluster.local`
    - `vlm-fintech-onboarding.svc.cluster.local:8000`

- **Do NOT add** `/v1/chat/completions`, `/api`, `/openai`, etc. at the end.

**About the port:**

- If the model service listens on the **default HTTP port 80**, you can omit the port entirely.
  Example: `my-model-service`
- If it uses a **non-standard port** (most often 8000 for vLLM, llama.cpp, Ollama with a custom
  port, etc.), you **must** specify the port.
  Example: `my-model-service:8000`
- The most common case inside Kubernetes: when models are running in the same cluster, use the
  **Kubernetes service name** (without external IP).

You can also set:

```bash
  --set secrets.VLM_MODEL_NAME="mistralai/Mistral-Small-3.2-24B-Instruct-2506" \
  --set secrets.VLM_TOKEN="your_access_token" \
```

These parameters are optional. Use them when needed:

- `VLM_MODEL_NAME`: Use when your deployment includes several LLMs.
- `VLM_TOKEN`: Use when your VLM requires an access token.

Wait until all pods are `Ready`, then port-forward to the UI with the following command:

```bash
kubectl port-forward svc/$name-aimsb-fintech-onboarding-ui 8080:8080 -n $namespace
```

To clean up:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set vlm.existingService="<my-vlm-service-ip-address>:8000" \
  | kubectl delete -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding

See the port-forward commands in the Quick Start sections above.

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (for example, Kubernetes Gateway or Istio),
you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**

- A Gateway named `https` must exist in the `envoy-gateway-system` namespace
  (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set http_route.enabled=true \
  # ... (other parameters as needed) ...
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the chart name, release name, and
the gateway's hostname. Use this command to produce the URL by querying the hostname from
the cluster:

```bash
echo "https://aimsb-fintech-onboarding-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```
