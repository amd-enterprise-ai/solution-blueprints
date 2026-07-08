<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# PDF to Podcast Deployment Guide

Solution Blueprints are provided as Helm Charts.
The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We do not recommend `helm install`, which by default uses a Secret to keep track of the related resources. This does not work well with Enterprise clusters that often have limitations on the kinds of resources that regular users are allowed to create.

This blueprint supports **AMD Instinct** (default) and **AMD Radeon** platforms. Unless otherwise specified, the commands below cover the default **Instinct** deployment. For deployment with Radeon, see:

- [Deploy on AMD Radeon](#amd-radeon-gpu)

## Multi-platform Support

The chart ships defaults for two platforms, selected with `--set global.platform=<platform>`: `instinct` (GPU, the default) and `radeon` (GPU). Each selects a matching AIM image and resource profile for the LLM; inspect them with `helm show values . --jsonpath '{.llm.platformDefaults}'`.

> **Helm note**: Built and tested on Helm 3.17 or higher. On Helm v4, if the piped `kubectl apply` is rejected, run `helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast --untar` first and template the local `./aimsb-pdf-to-podcast` directory instead.

Both the LLM and TTS services are deployed automatically via subchart dependencies (`aimchart-llm` and `aimchart-qwen-tts`). The environment variables `APP_LLM_URL` and `APP_TTS_BASE_URL` are auto-configured from the subchart service URLs.

### AMD Instinct (GPU, default)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  | kubectl apply -f - -n $namespace
```

### AMD Radeon (GPU)

To deploy the blueprint, run the following command:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external LLM

By default, any required AIMs are deployed by the helm chart. If you already have a compatible AIM deployed, you can use that instead, and reuse resources.

To use an existing deployment or external LLM, set the value `llm.existingService` to that endpoint. Then, any other values you pass in the `llm` mapping are simply ignored, and your existing service is used instead. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

Full example command:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set llm.existingService=$servicename \
  | kubectl apply -f - -n $namespace
```

### API Key and Model Configuration for External LLM

When using an external LLM service, you can optionally configure API authentication and model override:

- `llm.apiKey` (optional): Bearer token for API authentication
- `llm.model` (optional): Explicit model id to use

```bash
name="my-deployment"
namespace="my-namespace"
api_url="https://llm-api.example.com"
api_key="<YOUR_API_KEY>"
model_name="openai/gpt-oss-20b"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set llm.existingService=$api_url \
  --set llm.apiKey=$api_key \
  --set llm.model=$model_name \
  | kubectl apply -f - -n $namespace
```

### Using Kubernetes Secrets for API Key

```bash
name="my-deployment"
namespace="my-namespace"
secretname="my-secretname"
api_url="https://llm-api.example.com"

kubectl create secret generic $secretname -n $namespace \
  --from-literal=api-key="<YOUR_API_KEY>"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set llm.existingService=$api_url \
  --set llm.apiKeySecretRef.name=$secretname \
  --set llm.apiKeySecretRef.key=api-key \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external TTS

Similarly, to use an existing TTS service instead of the default `aimchart-qwen-tts` deployment, set `qwen-tts.existingService` to the endpoint. The TTS service must expose an OpenAI-compatible API (`POST /v1/audio/speech`).

```bash
name="my-deployment"
namespace="my-namespace"
ttsservice="my-tts-service"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set qwen-tts.existingService=$ttsservice \
  | kubectl apply -f - -n $namespace
```

If the TTS service requires an API key, pass it via:
```bash
  --set pythonServices.app.env.APP_TTS_API_KEY="<your_tts_api_key>"
```

## Default AIM image and GPU compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM: `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Using a custom image and imagePullSecrets

To use a custom version of the image from another repo, you can set the `image` and `imagePullSecrets`, if necessary, from the command line as follows:

```bash
imagerepository="my-repo/custom-pdf-to-podcast-application"
imagetag="0.0.1"
uiimagerepository="my-repo/custom-pdf-to-podcast-ui"
uiimagetag="0.0.1"
secretname="my-registry-secret"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set image.repository=$imagerepository \
  --set image.tag=$imagetag \
  --set uiImage.repository=$uiimagerepository \
  --set uiImage.tag=$uiimagetag\
  --set imagePullSecrets[0].name=$secretname \
  | kubectl apply -f - -n $namespace
```

## Configuration Highlights

- **LLM**: set `llm.existingService` to reuse an external LLM; otherwise the chart deploys the default via `aimchart-llm` dependency.
- **TTS**: set `qwen-tts.existingService` to reuse an external OpenAI-compatible TTS service; otherwise the chart deploys the default via `aimchart-qwen-tts` dependency. `APP_TTS_BASE_URL` is auto-configured from the subchart.
- **Secrets**: configure API and TTS keys under `pythonServices.app.env`:
  - `APP_TTS_API_KEY` - API key for the TTS service (if required by the TTS backend)
  - `APP_API_KEY` - Optional API key for authentication
  - `APP_CELERY_BROKER_URL` and `APP_CELERY_BACKEND_URL` - Auto-configured if not set
- **Storage**: adjust persistent volume settings in `values.yaml`:
  - `storage.ephemeral` - Temporary storage (20Gi default)
  - `storage.appStorage` - Shared storage for PDFs (10Gi default, ReadWriteMany)
  - `storage.dshm` - Shared memory size (32Gi default)
- **Resources**: adjust CPU and memory limits in `resources` section (default: 500m CPU requests, 4 CPU limits, 4Gi memory requests, 8Gi memory limits).

## Connecting

### Option 1: Port Forwarding

To connect to the UI, port-forward port 7860. The UI will then be available at <http://localhost:7860>.

```bash
kubectl port-forward svc/aimsb-pdf-to-podcast-$name-frontend 7860:7860 -n $namespace
```

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `envoy-gateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
    --set http_route.enabled=true \
     | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:

```bash
echo "https://aimsb-pdf-to-podcast-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```

## Clean Up

When you are finished, remove the deployed resources:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  | kubectl delete -f - -n $namespace
```
