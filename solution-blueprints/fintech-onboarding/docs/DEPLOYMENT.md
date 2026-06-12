<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

---

## GPU Support (AMD ROCm)

The service requires **at least 1 AMD GPU** to run. If you don't already have a VLM deployed,
you'll need an additional GPU - making a total of **at least 2 GPUs** for this deployment.
All necessary parameters for using GPU will be configured automatically.
---

## Quick Start

Start with k8s. You should have two ways:

### 1) If you don't have existing deployed VLM service:

Example a command to start service:

```
export name="fintech"
export namespace="fintech-onboarding"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  | kubectl apply -f - -n $namespace
```

Please wait for all pods Ready status, and after that you can make port forwarding for UI using
command:

```
kubectl port-forward svc/$name-aimsb-fintech-onboarding-ui 8080:8080 -n $namespace
```

The end of using:

```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  | kubectl delete -f - -n $namespace
```

### 2) If you already have existing deployed VLM service:

Example a command to start service:

```
export name="fintech"
export namespace="fintech-onboarding"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set vlm.existingService="129.212.190.161:8000" \
  | kubectl apply -f - -n $namespace
```

---
**Important notes about parameter `vlm.existingService`:**

- `vlm.existingService` is **only the base address of the model service**, without API path suffix
  `/v1` and without `http://` prefix.
  Correct examples:
    - `129.212.190.161:8000`
    - `mistralai-small-24B-Instruct`
    - `my-model.default.svc.cluster.local`
    - `vlm-fintech-onboarding.svc.cluster.local:8000`

- **Do NOT add** `/v1/chat/completions`, `/api`, `/openai` etc. at the end.

**About the port**

- If the model service listens on the **default http port 80** → you can omit the port entirely
  Example: `my-model-service`
- If it uses a **non-standard port** (most often 8000 for vLLM, llama.cpp, Ollama with custom
  port, etc.) → you **must** specify the port
  Example: `my-model-service:8000`
- The most common case inside Kubernetes: when models are running in the same cluster → use the
  **Kubernetes service name** (without external IP)

---
You can also set:

```
  --set secrets.VLM_MODEL_NAME="mistralai/Mistral-Small-3.2-24B-Instruct-2506" \
  --set secrets.VLM_TOKEN="your_access_token" \
```

this params is optional, but if need you can use it. `VLM_MODEL_NAME` - use in case when your
deployment include several LLMs.
`VLM_TOKEN` - use in case when for access to your VLM need a token.

Please wait for all pods Ready status, and after that you can make port forwarding for UI using
command:

```
kubectl port-forward svc/$name-aimsb-fintech-onboarding-ui 8080:8080 -n $namespace
```

The end of using:

```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fintech-onboarding \
  --set vlm.existingService="129.212.190.161:8000" \
  | kubectl delete -f - -n $namespace
```

### About HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.),
you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**

- A Gateway named `https` must exist in the `kgateway-system` namespace
  (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
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
