<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

## Prerequisites

Before deploying the Med Assist Voice Consultation blueprint, a cluster-admin must install the **STUNner Operator**
— a Kubernetes-native WebRTC media gateway used for routing browser media
traffic to LiveKit. This is a one-time cluster-level operation that installs the operator and
creates a shared `stunner` GatewayClass used by all blueprint deployments on the cluster.

Run the provided script once per cluster:

```bash
cd solution-blueprints/med-assist
./install-prerequisites.sh
```

Requirements:

- kubectl configured and pointing at your target cluster
- Helm 3.17 or higher installed
- cluster-admin or rights to create ClusterRole, ClusterRoleBinding, and CRDs.

The script installs:

- STUNner Gateway Operator (Deployment, ClusterRoles, CRDs) into the `stunner-system` namespace
- A shared cluster-wide `GatewayClass` named `stunner`

After the script completes, regular users (without cluster-admin privileges) can deploy and remove
the blueprint without errors. Each blueprint deployment creates its own namespace-scoped resources (
Gateway, GatewayConfig, UDPRoute) that the shared operator reconciles independently — multiple
blueprint deployments can coexist on the same cluster without conflicts.

> **Important:** Do not use `kubectl delete` on the STUNner operator pods or scale them to zero
> while blueprints are running. The operator is shared cluster infrastructure. To fully remove
> STUNner, use `./install-prerequisites.sh --uninstall` after all blueprints have been removed.

To uninstall:

```bash
./install-prerequisites.sh --uninstall
```

> **Note:** STUNner routes media traffic from the browser to LiveKit. In most setups, you no longer
> need to open UDP ports `50000-60000` on worker nodes.

# Med Assist Voice Consultation Deployment Guide

Solution Blueprints are provided as Helm Charts. The recommended approach to deploy them is to pipe the output of `helm template` to
`kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related
resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of
resources that
regular users are allowed to create.

This blueprint supports **AMD Instinct** (default) and **AMD Radeon** platforms. Unless otherwise specified, the commands below cover the default **Instinct** deployment. For deployment with Radeon, see:

- [Deploy on AMD Radeon](#amd-radeon-gpu)

An example for command-line usage (see **LiveKit WebSocket URL** section for how to set `frontend_livekit_ws_url`):

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit.example.com"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=httpRoute" \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

By default, the chart deploys LiveKit, LLM, and Qwen ASR dependencies in addition to the blueprint services.

> **Note:** This deployment guide intentionally does **not** cover configuring or operating LiveKit in horizontally scaled or highly available setups
> (for example, multi-replica deployments, Redis-backed coordination, or advanced clustering topologies). For production-grade LiveKit scaling,
> please refer to the official LiveKit documentation and your platform’s best practices.

## Multi-platform Support

The chart ships defaults for two platforms, selected with `--set global.platform=<platform>`: `instinct` (GPU, the default) and `radeon` (GPU). Each sets a matching AIM image and resource profile for the LLM; inspect them with `helm show values . --jsonpath '{.llm.platformDefaults}'`.

> **Helm note**: Built and tested on Helm 3.17 or higher. On Helm v4, if the piped `kubectl apply` is rejected, run `helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist --untar` first and template the local `./aimsb-med-assist` directory instead.

### AMD Instinct (GPU, default)

This is the default platform; the deployment commands in this guide run the LLM on AMD Instinct GPUs with no extra flags. The default LLM is Meta Llama 3.3 70B Instruct (`aim-meta-llama-llama-3-3-70b-instruct`).

### AMD Radeon (GPU)

On Radeon the chart deploys a different, Radeon-optimized LLM — Qwen3-VL 8B Instruct (`aim-radeon-qwen-qwen3-vl-8b-instruct`) instead of Llama 3.3 70B. Add `--set global.platform=radeon` to any deploy command to select the Radeon AIM defaults:

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit.example.com"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=httpRoute" \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set global.platform=radeon \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## LiveKit WebSocket URL

Media traffic from the browser to LiveKit is routed through **STUNner** regardless of the exposure
mode.

Exposure is controlled by `livekit.exposure.mode`:

- **`httpRoute`** — chart creates a LiveKit `HTTPRoute` (Gateway API). It does **not** create the
  parent-chart NodePort `Service`. If `pythonServices.frontend.env.LIVEKIT_WS_URL` is empty, chart
  auto-generates
  `wss://<release.fullname>-livekit.<livekit.httpRoute.hostSuffix>` (same host shape as the
  `HTTPRoute` match). Otherwise set `LIVEKIT_WS_URL` explicitly, or pass only
  `livekit.httpRoute.hostSuffix` (DNS zone after `*-livekit.`, e.g. `example.com`).
- **`nodePort`** — chart creates `<release>-livekit-nodeport` (NodePort). If
  `pythonServices.frontend.env.LIVEKIT_WS_URL` is empty, chart auto-generates
  `ws://<livekit.nodePortService.nodeAddress>:<livekit.nodePortService.nodePort>`.

The agent service can still use in-cluster LiveKit automatically when
`pythonServices.agent.env.LIVEKIT_WS_URL` is left empty.

### Example: `httpRoute` (Gateway / HTTPRoute)

**Option A — auto `LIVEKIT_WS_URL` from DNS suffix** (Helm cannot read the Gateway object; pass the
zone that matches your listener hostname, e.g. from
`kubectl get gtw https -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}'` —
strip `*` and use the rest as `hostSuffix`):

```bash
name="my-deployment"
namespace="my-namespace"
# e.g. listener hostname *.example.com → use example.com
host_suffix="example.com"

helm template "$name" oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=httpRoute" \
  --set "livekit.httpRoute.hostSuffix=$host_suffix" \
  --namespace $namespace \
  | kubectl apply -f - -n "$namespace"
```

**Option B — explicit `LIVEKIT_WS_URL`** (same result as Option A when names line up):

```bash
name="my-deployment"
namespace="my-namespace"

gateway_suffix=$(kubectl get gtw https -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' | tr -d '*')
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit$gateway_suffix"

helm template "$name" oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=httpRoute" \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --namespace $namespace \
  | kubectl apply -f - -n "$namespace"
```

### Example: `nodePort`

```bash
name="my-deployment"
namespace="my-namespace"

node_address=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
if [ -z "$node_address" ]; then
  node_address=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
fi

helm template "$name" oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=nodePort" \
  --set "livekit.nodePortService.nodeAddress=$node_address" \
  --set "livekit.nodePortService.nodePort=32080" \
  --namespace $namespace \
  | kubectl apply -f - -n "$namespace"
```

(You can omit `pythonServices.frontend.env.LIVEKIT_WS_URL` in `nodePort` mode when `nodeAddress` and
`nodePort` are set; the chart will build `ws://...` for the frontend.)

**Firewall / security groups (required for `nodePort`):** Allow inbound **TCP** to the configured
NodePort (default `32080`) for LiveKit signaling. Thanks to STUNner, opening the large UDP media
port range (`50000-60000`) is usually not needed.

## Using an existing LiveKit service

If you already run LiveKit separately, you can disable the bundled LiveKit subchart and point both
services to your existing endpoint.

- Disable bundled LiveKit: `livekit.enabled=false`
- Set frontend URL: `pythonServices.frontend.env.LIVEKIT_WS_URL=wss://<your-livekit-host>`
- Set agent URL: `pythonServices.agent.env.LIVEKIT_WS_URL=wss://<your-livekit-host>`
- Set matching credentials for both services:
    - `pythonServices.frontend.env.LIVEKIT_API_KEY` and
      `pythonServices.frontend.env.LIVEKIT_API_SECRET`
    - `pythonServices.agent.env.LIVEKIT_API_KEY` and `pythonServices.agent.env.LIVEKIT_API_SECRET`

Example:

```bash
name="my-deployment"
namespace="my-namespace"
existing_livekit_ws_url="wss://livekit.example.com"
livekit_api_key="my-livekit-key"
livekit_api_secret="my-livekit-secret"

helm template "$name" oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.enabled=false" \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$existing_livekit_ws_url" \
  --set "pythonServices.agent.env.LIVEKIT_WS_URL=$existing_livekit_ws_url" \
  --set "pythonServices.frontend.env.LIVEKIT_API_KEY=$livekit_api_key" \
  --set "pythonServices.frontend.env.LIVEKIT_API_SECRET=$livekit_api_secret" \
  --set "pythonServices.agent.env.LIVEKIT_API_KEY=$livekit_api_key" \
  --set "pythonServices.agent.env.LIVEKIT_API_SECRET=$livekit_api_secret" \
  --namespace $namespace \
  | kubectl apply -f - -n "$namespace"
```

## LiveKit UDP firewall requirement (with STUNner)

With **STUNner** integration, direct exposure of LiveKit UDP media ports (`50000-60000`) on worker
nodes is usually **not required**. STUNner acts as the external WebRTC media gateway.

What you still need:

- For `nodePort` mode: allow inbound **TCP** to the configured NodePort (default `32080`) for
  LiveKit signaling.
- Ensure your Gateway listener (usually ports 80/443) is reachable from clients.

See the STUNner documentation for Gateway-specific firewall details.

## Using an existing deployment or external LLM

By default, any required AIMs are deployed by the helm chart. If you already have a compatible AIM
deployed, you can use that instead, and reuse resources.

To use an existing deployment or external LLM, set the value `llm.existingService` to that endpoint.
Then, any other values you pass in the `llm` mapping are simply ignored, and your existing service
is used instead. You should use the Kubernetes Service name, or if the service is in a different
namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If
needed, you can pass a whole URL.

Full example command:

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit$(kubectl get gtw https -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' | tr -d '*')"
llm_service="my-llm-service"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set "llm.existingService=$llm_service" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external ASR

You can use an existing ASR service instead of the bundled `qwen-asr` dependency. The ASR endpoint
must expose an **OpenAI-compatible audio transcription API** (for example,
`POST /v1/audio/transcriptions`), so that the agent can call it using the same schema.

- Set `qwen-asr.existingService` to point to your ASR endpoint:
    - Kubernetes Service name in the same namespace, e.g. `my-asr-service`
    - Fully qualified in-cluster service: `<SERVICE>.<NAMESPACE>.svc.cluster.local:<PORT>`
    - Or a full URL

- Configure the agent to use that ASR with the right model and credentials:
    - `pythonServices.agent.env.STT_MODEL` — ASR model name understood by your OpenAI-compatible
      endpoint
    - `pythonServices.agent.env.STT_API_KEY` — API key or token for that ASR

Example:

```bash
name="my-deployment"

namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit$(kubectl get gtw https -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' | tr -d '*')"
asr_service="my-asr-service"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set "qwen-asr.existingService=$asr_service" \
  --set "pythonServices.agent.env.STT_BASE_URL=https://asr.example.com" \
  --set "pythonServices.agent.env.STT_MODEL=my-asr-model" \
  --set "pythonServices.agent.env.STT_API_KEY=$MY_ASR_API_KEY" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## Deploying LiveKit on a specific node

You can pin LiveKit pods to a specific Kubernetes node with `livekit.nodeSelector`.

Example (pin to hostname-labeled node):

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit.example.com"
livekit_node="worker-gpu-01"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set-string "livekit.nodeSelector.kubernetes\.io/hostname=$livekit_node" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

After applying node pinning, ensure the NodePort for signaling (default `32080`) is reachable.
Thanks to STUNner, you typically do **not** need to open UDP `50000-60000` on that node.

## Exposing LiveKit via parent chart NodePort service

When `livekit.exposure.mode=nodePort`, this chart creates a dedicated NodePort `Service`:

- Name: `<release-name>-livekit-nodeport`
- Port: `livekit.nodePortService.port` (default `7880`)
- NodePort: `livekit.nodePortService.nodePort` (default `32080`)

Example:

```bash
name="my-deployment"
namespace="my-namespace"
node_address="<your-ip-node-address>"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=nodePort" \
  --set "livekit.nodePortService.nodeAddress=$node_address" \
  --set "livekit.nodePortService.nodePort=32080" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

Notes:

- **Firewall:** configure your network so clients can reach the **TCP NodePort** (
  `livekit.nodePortService.nodePort`, default `32080`) on the node IP. Thanks to **STUNner**,
  opening the UDP media range (`50000-60000`) and TCP `7881` on LiveKit nodes is usually **not
  required**.
- Exposing signaling is not enough for WebRTC by itself. Make sure your Gateway listener (usually
  80/443) is reachable from clients.
- For browser usage, prefer `wss://` with DNS + TLS and set
  `pythonServices.frontend.env.LIVEKIT_WS_URL` explicitly.

To reach LiveKit from outside without Gateway, resolve the NodePort and node address:

```bash
namespace="my-namespace"
name="my-deployment"

livekit_svc="$name-livekit-nodeport"
livekit_node_port=$(kubectl get svc "$livekit_svc" -n "$namespace" -o jsonpath='{.spec.ports[?(@.name=="ws")].nodePort}')
node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')

echo "NodePort endpoint: ws://${node_ip}:${livekit_node_port}"
```

If nodes have no `ExternalIP`, use a routable internal IP (for VPN/private networks) or put a DNS/LB
in front and use `wss://<fqdn>`.

### How to get `nodeAddress` for `livekit.nodePortService.nodeAddress`

Use the first available node address from the cluster:

```bash
node_address=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')

if [ -z "$node_address" ]; then
  node_address=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
fi

echo "$node_address"
```

> **Important:** this snippet uses `.items[0]` (the first node returned by the API), which is
> convenient for quick tests but not always the best routable node for external clients. For
> production, prefer a known reachable node address or a stable DNS/LB endpoint.

Then pass it to Helm:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "livekit.exposure.mode=nodePort" \
  --set "livekit.nodePortService.nodeAddress=$node_address" \
  --set "livekit.nodePortService.nodePort=32080" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and GPU compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM:
`amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1`

On newer GPUs, this default image may not be the best match and can fail to start or run
sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See
the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html)
for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## Using custom images and imagePullSecrets

To use custom frontend/agent/dependency images, override image values from CLI or a values file.

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit.example.com"
backend_image_repo="my-repo/custom-med-assist-backend"
backend_tag="0.0.1"
ui_image_repo="my-repo/custom-med-assist-ui"
ui_tag="0.0.1"
secret_name="my-registry-secret"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set "image.repository=$backend_image_repo" \
  --set "image.tag=$backend_tag" \
  --set "uiImage.repository=$ui_image_repo" \
  --set "uiImage.tag=$ui_tag" \
  --set "imagePullSecrets[0].name=$secret_name" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

## Connecting

### 1. Connecting via port-forwarding

- Frontend UI is exposed on port `7860` by the `frontend` service.
- For local debugging:

```bash
kubectl port-forward "svc/aimsb-med-assist-$name-frontend" 7860:7860 -n $namespace
```

Then open `http://localhost:7860`.

### 2. Connecting via HTTPRoute

If your cluster has a Gateway API compatible gateway, you can route frontend traffic through
HTTPRoute.

**Prerequisites:**

- A Gateway named `https` in namespace `envoy-gateway-system` (or adapt templates/values to your gateway
  naming).
- A valid external LiveKit WebSocket URL for frontend env.

Enable frontend HTTPRoute creation:

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://aimsb-med-assist-$name-livekit.example.com"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --set "http_route.enabled=true" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

When `livekit.enabled=true`, the chart also creates a LiveKit HTTPRoute resource (
`livekit-httproute.yaml`) targeting service `<release>-livekit` on port 80.

**Obtaining frontend URL pattern:**

The frontend HTTPRoute host pattern is based on release fullname:

```bash
echo "https://aimsb-med-assist-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```

Use your gateway/controller tooling to resolve the exact routable hostname in your cluster.

## Clean Up

When you are finished, remove the deployed resources by rendering the same command you used to deploy and piping it to `kubectl delete`:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-med-assist \
  --set "pythonServices.frontend.env.LIVEKIT_WS_URL=$frontend_livekit_ws_url" \
  --namespace $namespace \
  | kubectl delete -f - -n $namespace
```

If you installed the STUNner prerequisites for this cluster and no longer need them, uninstall them separately:

```bash
cd solution-blueprints/med-assist
./install-prerequisites.sh --uninstall
```
