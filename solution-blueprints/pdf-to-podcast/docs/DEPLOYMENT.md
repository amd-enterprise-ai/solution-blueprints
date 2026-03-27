<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Helm deployment

Solution Blueprints are provided as Helm charts. Recommended flow: render with `helm template` and pipe to `kubectl apply -f -` (avoids Helm release Secrets that may be restricted).

## ElevenLabs API key

- Sign up at https://elevenlabs.io/. New accounts typically get ~10,000 free credits (around 10 minutes of TTS audio).
- Create an API key with TTS access and pass it as `pythonServices.app.env.APP_ELEVENLABS_API_KEY`.
- If you only need the no‑TTS mode, you can omit the ElevenLabs API key entirely.

## Deploy

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
  | kubectl apply -f - -n $namespace
```

LLM is deployed via the `aimchart-llm` dependency by default.

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
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and GPU compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM: `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.10.0`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
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
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
  | kubectl apply -f - -n $namespace
```

## Connecting

### 1. Connecting via port-forwarding

- Frontend UI is exposed on port `7860` by the `frontend` service.
- For local debugging:

```bash
kubectl port-forward svc/aimsb-pdf-to-podcast-$name-frontend 7860:7860 -n $namespace
```

Then open `http://localhost:7860`.

### 2. Connecting via HTTPRoute

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:
(notice, the command contains an existing Llm service running in the cluster).

```bash
key="your_ELEVENLABS_API_KEY"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-pdf-to-podcast \
    --set http_route.enabled=true \
    --set llm.existingService=$servicename \
    --set pythonServices.app.env.APP_ELEVENLABS_API_KEY=$key \
     | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:

```bash
echo "https://aimsb-pdf-to-podcast-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```
