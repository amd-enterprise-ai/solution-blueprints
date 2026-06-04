<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->


# Telecom Assistant Blueprint

The Telecom Assistant is a real-time AI-powered voice support system designed for telecom customer service.
When a user speaks, their voice is streamed via LiveKit to the VoiceAgent, which transcribes it using the
STT model and forwards the resulting text to the LLM. Before generating a response, the LLM enriches its
context by retrieving relevant information from ChromaDB using semantic embeddings, as well as querying
customer-specific data such as billing and account details through the BSSGateway. The generated response
is then converted back to speech by the TTS model and streamed to the user in real time. If the conversation
results in a support request, it is automatically registered in LibreDesk, while Redis ensures fast session
management and state persistence across the interaction.

## Quick start (Helm)

### Prerequisites
- Run `./install-prerequisites.sh` to install the **STUNner Operator** (requires `cluster-admin` privileges or rights to create `ClusterRole`, `ClusterRoleBinding`, and CRDs). This is needed once per cluster.

Media traffic from the browser to LiveKit is routed through **STUNner**.

### Required LiveKit WebSocket URL

- Set `mainServices.frontend.env.LIVEKIT_URL` to an externally reachable LiveKit WebSocket URL used by the browser to connect to LiveKit via your Gateway.
- If this value is empty, chart rendering fails.
- The agent service can still use in-cluster LiveKit automatically when `mainServices.agent.env.LIVEKIT_URL` is left empty.

More details on how to derive this URL in a Gateway/HTTPRoute setup are available in `docs/DEPLOYMENT.md` under the **LiveKit WebSocket URL** section.


```bash
cd solution-blueprints/telecom-assistant
helm dependency build

name="my-deployment"
namespace="my-namespace"
frontend_livekit_ws_url="wss://livekit-aimsb-telecom-assistant-${name}$(kubectl get gtw https -n kgateway-system -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' | tr -d '*')"

helm template $name . \
  --set "mainServices.frontend.env.LIVEKIT_URL=$frontend_livekit_ws_url" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

- By default, LLM, STT and TTS are provided by the `llm`, `stt` and `tts` dependencies.
- With **STUNner** integration, media traffic from the browser is routed through the STUNner Gateway. Direct exposure of LiveKit UDP media ports (`50000-60000`) on worker nodes is usually **not required**.
- LiveKit signaling remains exposed via HTTPRoute (Gateway API).
- Ports/env are in `values.yaml`.
- Set secrets via `--set`/override file or Kubernetes Secret refs.

## List of deployable services

| Service         | Description                                                                                                           |
|-----------------|-----------------------------------------------------------------------------------------------------------------------|
| **STUNner**     | Kubernetes-native WebRTC media gateway (STUN/TURN) that routes browser media traffic to LiveKit                       |
| BSSGateway      | Handles integration with the BSS (Business Support System), enabling access to customer data and billing information  |
| VoiceAgent      | Core service that orchestrates the conversation flow between the user, LLM, STT, and TTS models                       |
| Frontend        | Web-based user interface for interacting with the assistant                                                           |
| Redis           | In-memory data store used for caching and session management                                                          |
| LiveKit         | Real-time audio/video transport layer for streaming voice between the user and the agent (media routed via STUNner)   |
| ChromaDB        | Vector database used for storing and retrieving embeddings for context-aware responses                                |
| Postgres        | Relational database for Libredesk                                                                                     |
| LibreDesk       | Helpdesk integration for creating and managing customer support tickets                                               |
| STT Model       | Speech-to-Text model that transcribes user voice input into text                                                      |
| LLM Model       | Large Language Model responsible for generating responses based on user input and retrieved context                   |
| TTS Model       | Text-to-Speech model that converts the LLM response into audio for the user                                           |
| Embedding Model | Generates vector embeddings from text for semantic search and retrieval in ChromaDB                                   |

## Docs and architecture

- Full docs: `docs/README.md`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture diagram (light): `docs/architecture-diagram-light-scheme`
- Architecture diagram (dark): `docs/architecture-diagram-dark-scheme`

## Terms of Use

AMD Solution Blueprints are released under the MIT License. Third-party software and materials are governed by their respective licenses.
