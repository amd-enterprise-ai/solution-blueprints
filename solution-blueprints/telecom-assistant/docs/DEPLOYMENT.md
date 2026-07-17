<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Telecom Assistant Deployment Guide

## Prerequisites

Before deploying the Telecom Assistant blueprint, you must install the **STUNner Operator** — a Kubernetes-native WebRTC media gateway used for routing browser media traffic to LiveKit.

Run the provided script once per cluster:

```bash
cd solution-blueprints/telecom-assistant
./install-prerequisites.sh
```
Requirements:
- kubectl configured and pointing at your target cluster
- helm v3 installed
- cluster-admin or rights to create ClusterRole, ClusterRoleBinding, and CRDs.

To uninstall:

```bash
./install-prerequisites.sh --uninstall
```

> **Note:** STUNner routes media traffic from the browser to LiveKit. UDP ports `50000-60000` on worker nodes do **not** need to be opened. However, TCP access to the LiveKit signaling port (NodePort or Gateway port 80/443) is still required.

Solution Blueprints are provided as Helm Charts. The recommended approach to deploy them is to pipe the output of `helm template` to
`kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related
resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of
resources that
regular users are allowed to create.

An example for command-line usage:
```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://livekit.example.com"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --namespace $namespace \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  | kubectl apply -f - -n $namespace
```

## LiveKit WebSocket URL

Media traffic from the browser to LiveKit is routed through **STUNner** regardless of the exposure mode.

- Set `mainServices.frontend.env.LIVEKIT_URL` to an externally reachable LiveKit WebSocket URL.
- If this value is empty, chart rendering fails.
- The agent service can still use in-cluster LiveKit automatically when
  `mainServices.agent.env.LIVEKIT_URL` is left empty.

For the **frontend** (the URL the browser uses to connect to LiveKit WebSockets via the Gateway),
the value for `LIVEKIT_URL` must be supplied when deploying; the chart cannot set it automatically.
At render time (`helm template`) the chart has no access to the cluster, and the external hostname
is determined by your Gateway, DNS, and how you expose the service—so it has to be provided (or
derived with the command below) by the deployer. The frontend runs in the user's browser, so it
cannot use in-cluster addresses; it must use the same hostname the Gateway exposes (e.g.
`livekit.<gateway-domain>`) so that WebSocket connections are routed correctly to the LiveKit
service. The URL has the form `wss://livekit` + hostname (with wildcards removed). The chart’s
HTTPRoute for LiveKit targets the default Gateway `https` in namespace `envoy-gateway-system` and
listener `https`; if your cluster uses that setup, you can build the frontend WebSocket URL like
this:

```bash
frontend_livekit_ws_url="wss://livekit-aimsb-telecom-assistant-${name}$(kubectl get gtw https -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' | tr -d '*')"
```

Use this value when deploying, e.g. `--set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url"`.

## LiveKit firewall requirements (with STUNner)

STUNner acts as the external WebRTC media gateway and handles all media routing between the browser and LiveKit.

| Traffic type    | Ports                                               | Required?                   |
|-----------------|-----------------------------------------------------|-----------------------------|
| Media (RTP/UDP) | `50000-60000` on worker nodes                       | **No** — handled by STUNner |
| Signaling (TCP) | NodePort (if `nodePort` mode) or Gateway `80`/`443` | **Yes**                     |

In short: you do **not** need to open the wide UDP range. You **do** need TCP access to the LiveKit signaling endpoint — either the configured NodePort or the Gateway listener, depending on your exposure mode.

See the STUNner documentation for Gateway-specific firewall details.

## Using an existing deployment or external services
By default, any required AIMs (STT, LLM, TTS, VLM, Embedding, ChromaDB) are deployed by the helm chart. If you already have compatible services deployed, you can use them instead, and reuse resources.

To use an existing deployment, set the `existingService` value for the respective component. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

> **Note:** This deployment guide intentionally does **not** cover configuring or operating LiveKit in horizontally scaled or highly available setups
> (for example, multi-replica deployments, Redis-backed coordination, or advanced clustering topologies). For production-grade LiveKit scaling,
> please refer to the official LiveKit documentation and your platform’s best practices.

By default, the following models are used:

| Role | Default Model                                 |
|------|-----------------------------------------------|
| STT  | Qwen3 ASR 1.7B                                |
| LLM  | GPT OSS 120B                                  |
| TTS  | Qwen3 TTS 12Hz 1.7B CustomVoice               |
| VLM  | mistralai/Mistral-Small-3.2-24B-Instruct-2506 |

> **Note:** Compatibility with other models for the same purposes is not guaranteed.

To override the default values, set the following environment variables:

| Variable                              | Description                                |
|---------------------------------------|--------------------------------------------|
| `mainServices.agent.env.STT_MODEL`   | STT model name                             |
| `mainServices.agent.env.STT_API_KEY` | API key for the STT service (if required)  |
| `mainServices.agent.env.LLM_MODEL`   | LLM model name                             |
| `mainServices.agent.env.LLM_API_KEY` | API key for the LLM service (if required)  |
| `mainServices.agent.env.TTS_MODEL`   | TTS model name                             |
| `mainServices.agent.env.TTS_API_KEY` | API key for the TTS service (if required)  |

>If you are using external models, follow the instructions in the sections below

### External STT
Set `stt.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set stt.existingService="http://my-stt-service:8000" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### External LLM
Set `llm.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set llm.existingService="http://my-llm-service:8000" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### External TTS
Set `tts.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set tts.existingService="http://my-tts-service:8000" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### External Embedding Service
Set `embedding.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set embedding.existingService="http://my-embedding-service:7997" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### External ChromaDB
Set `chromadb.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set chromadb.existingService="http://my-chromadb-service:8000" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### External VLM
Set `vlm.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --set vlm.existingService="http://<my-vlm-service>:8000/v1" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```
> **WARNING**
> Url for vlm.existingService should include '/v1'

### Deploy with LiveKit

To deploy LiveKit we use official Helm chart for LiveKit.  You need to add repository to your helm repo:
```bash
helm repo add livekit https://helm.livekit.io
```

Then perform dependencies update and build.

Now you can execute:

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://livekit.example.com"

helm template $name . \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

### Deploying LiveKit on a specific node

You can pin LiveKit pods to a specific Kubernetes node with `livekit.nodeSelector`.

Example (pin to hostname-labeled node):

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://livekit.example.com"
livekit_node="worker-gpu-01"

helm template $name . \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  --set-string "livekit.nodeSelector.kubernetes\.io/hostname=$livekit_node" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

After applying node pinning, ensure the NodePort for signaling (TCP) is reachable from clients. UDP ports `50000-60000` do not need to be opened on that node — STUNner handles media routing.


## Default AIM image and GPU compatibility

By default, the chart deploys OpenAI GPT OSS 120B model with this AIM: `amdenterpriseai/aim-openai-gpt-oss-120b:0.11.1`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name . \
  --set llm.image=amdenterpriseai/aim-openai-gpt-oss-120b:<NEWER_TAG> \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

> **Note:** You can combine all of these flags as needed.

## Postgres Data Migration
When the Helm chart is deployed, a Kubernetes Job (`postgres-dump-restore-job`) is automatically executed as a
post-install hook. This job performs an initial data migration into the LibreDesk PostgreSQL database, seeding it
with the minimum required entities for the system to function correctly.

### Why This Migration Is Needed
LibreDesk requires two entities to be present in the database before it can process support tickets programmatically:

**Agent** — A pre-created agent account is required to generate API credentials (API key and API secret). These
credentials are used as the authorization token for LibreDesk API requests made by the Voice Agent.
**Inbox** — A pre-created inbox is required because the Inbox ID is a mandatory field when creating a ticket via the
LibreDesk API. Without an existing inbox, ticket creation requests will fail.

### Why Automated Seeding Is Necessary
There is no programmatic way to create these entities without prior authentication. Normally, both the Agent and the
Inbox must be created manually by logging into LibreDesk with an admin account and adding them through the UI. Since
this manual step is not feasible in an automated deployment pipeline, the migration job seeds the database directly
with the required records after LibreDesk has fully started.

## Connecting

### 1. Connecting via port-forwarding

- Frontend UI is exposed on port `3000` by the `frontend` service.
- For proper operation with this approach, the LiveKit service also needs to be exposed externally.
 For local debugging:

```bash
kubectl port-forward "svc/aimsb-telecom-assistant-$name-frontend" 3000:3000 -n $namespace
```

Then open `http://localhost:3000`.

### 2. Connecting via HTTPRoute

If your cluster has a Gateway API compatible gateway, you can route frontend traffic through HTTPRoute.

**Prerequisites:**

- A Gateway named `https` in namespace `envoy-gateway-system` (or adapt templates/values to your gateway
  naming).
- A valid external LiveKit WebSocket URL for frontend env.

**Note:** Media (RTP) traffic is routed through STUNner, so opening the wide UDP port range (`50000-60000`) on LiveKit nodes is usually not required. However, TCP access to the signaling port (NodePort or Gateway) is still needed.

Enable frontend HTTPRoute creation:

```bash
name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://livekit.example.com"

helm template $name . \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  --set "http_route.enabled=true" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

When `livekit.enabled=true`, the chart also creates a LiveKit HTTPRoute resource (`livekit-httproute.yaml`) targeting service `<release>-livekit` on port 80.

**Obtaining frontend URL pattern:**

The frontend HTTPRoute host pattern is based on release fullname:

```bash
echo "https://aimsb-telecom-assistant-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
```

Use your gateway/controller tooling to resolve the exact routable hostname in your cluster.

### Clean Up

When you are finished, remove the deployed resources:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-telecom-assistant \
  --namespace $namespace \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  # ... (same parameters as deployment) ...
  | kubectl delete -f - -n $namespace
```
