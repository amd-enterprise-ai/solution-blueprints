<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Med Assist Voice Consultation

This blueprint provides an end-to-end realtime med-assist voice consultation workflow. It uses LiveKit for media transport, Qwen ASR for speech-to-text, and an LLM backend for generating consultation output. The solution is packaged as a Helm chart for Kubernetes deployment.

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="Diagram of a med-assist voice consultation workflow: the user joins a LiveKit session from the browser; an agent transcribes the doctor–patient call using an ASR service and, with support from an LLM, generates a structured SOAP consultation report for the user." src="architecture-diagram-light-scheme.png">
</picture>

## STUNner Integration
Media traffic from the browser-based frontend to the **LiveKit** service now flows through **STUNner**, a Kubernetes-native WebRTC media gateway. STUNner acts as a STUN/TURN gateway between external clients and the LiveKit pods, simplifying NAT traversal and firewall configuration in cloud-native environments. This replaces direct exposure of LiveKit media ports in many setups.

## Key Features

- Realtime voice consultation flow over LiveKit with a browser-based frontend.
- Continuous transcription of the doctor–patient call via Qwen ASR during the session.
- LLM-powered generation of a structured SOAP-style consultation report (Subjective, Objective, Assessment, Plan) from the call transcript.
- Flexible deployment model: deploy bundled LLM/ASR dependencies or reuse existing OpenAI-compatible endpoints.

## Components

- **STUNner**('stunner') - Kubernetes-native WebRTC media gateway (STUN/TURN server) that acts as a secure entry point for media traffic between the browser-based frontend and LiveKit.
- **LiveKit service** (`livekit`) - WebRTC room and media transport.
- **Agent service** (`pythonServices.agent`) - Handles transcription and LLM interactions.
- **Frontend service** (`pythonServices.frontend`) - Web UI on port 7860 for session interaction.
- **LLM service** (`llm`) - Default LLM backend dependency (can be replaced via `llm.existingService`).
- **ASR service** (`qwen-asr`) - Default speech-to-text backend (can be replaced via `qwen-asr.existingService`).

## System Requirements

- Kubernetes cluster with GPU-capable worker nodes for LLM/ASR inference workloads.
- **STUNner Operator** must be installed on the cluster to provide the WebRTC media gateway functionality. You can install it manually or by running the provided `install-prerequisites.sh` script (requires `cluster-admin` privileges or rights to create `ClusterRole`, `ClusterRoleBinding`, and CRDs).
- Network configuration that allows client access to frontend and LiveKit endpoints (media traffic is routed through STUNner).
- LiveKit media traffic requires preliminary network/firewall configuration. With STUNner integration, direct exposure of LiveKit media ports on worker nodes is no longer required in most setups.
  - If you use **`livekit.exposure.mode=nodePort`**, you must still allow **inbound TCP** to the chosen **NodePort** (default `32080`) for WebSocket signaling.
  - For details on configuring STUNner, LiveKit media routing, and firewall rules, see `docs/DEPLOYMENT.md`.
- Resource requirements (defaults in `values.yaml` for `agent` and `frontend` services):
  - **Total CPU requests**: 1 CPU (agent: 500m, frontend: 500m)
  - **Total CPU limits**: 4 CPU (agent: 2, frontend: 2)
  - **Total memory requests**: 2Gi (agent: 1Gi, frontend: 1Gi)
  - **Total memory limits**: 4Gi (agent: 2Gi, frontend: 2Gi)
- Model serving resources (default bundled dependencies):
  - **LLM (`llm`)**: requests/limits `amd.com/gpu: 1`, `cpu: 4`, `memory: 64Gi`, plus ephemeral storage `512Gi`.
  - **ASR (`qwen-asr`)**: requests/limits `amd.com/gpu: 1` (for `Qwen/Qwen3-ASR-1.7B`), with memory sizing depending on your ASR image/config.
  - **GPU planning baseline**: plan for at least **2 GPUs total** when running both bundled model services (`1` for LLM + `1` for ASR).
  - If you use `llm.existingService` and/or `qwen-asr.existingService`, GPU requirements are defined by those external services.

## Usage (overview)

1) Install prerequisites: run `./install-prerequisites.sh` to deploy the **STUNner Operator** (requires `cluster-admin` privileges or rights to create ClusterRole, ClusterRoleBinding, and CRDs).
2) Build dependencies and deploy with `helm template ... | kubectl apply -f -`.
3) Set `pythonServices.frontend.env.LIVEKIT_WS_URL` to your external LiveKit WebSocket URL.
4) Optionally set `llm.existingService` and/or `qwen-asr.existingService` to reuse existing backends.
5) Access the frontend via port-forwarding or HTTPRoute.

See `docs/DEPLOYMENT.md` for complete commands, STUNner configuration details, and examples.

## Configuration Highlights

- **LLM**: set `llm.existingService` to reuse an external LLM; otherwise the chart deploys the default LLM via the `llm` dependency.
- **ASR (OpenAI-compatible)**: set `qwen-asr.existingService` to reuse an external ASR that exposes an OpenAI-compatible audio transcription API.
- **Agent Secrets**: configure LiveKit and model access under `pythonServices.agent.env`:
  - `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — LiveKit credentials used by agent.
  - `LLM_API_KEY` — API key for the LLM backend when required by your `llm` deployment or external endpoint.
  - `STT_API_KEY` — API key for the external ASR service when using `qwen-asr.existingService`.
  - `STT_MODEL` - Model name for the external ASR service when using `qwen-asr.existingService`.
- **Frontend Secrets**: configure LiveKit and model access under `pythonServices.frontend.env`:
  - `LIVEKIT_WS_URL` — external LiveKit WebSocket URL; without this value chart rendering fails. See `docs/DEPLOYMENT.md` for details and examples.
  - `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — LiveKit credentials used by frontend.
- **Networking**:
  - `http_route.enabled=true` enables frontend HTTPRoute generation.
  - LiveKit HTTPRoute is created when `livekit.enabled=true`.
  - With **STUNner** integration, direct exposure of LiveKit UDP media ports (`50000-60000`) on worker nodes is usually **not required**. STUNner handles media traffic routing.
  - If you use **`livekit.exposure.mode=nodePort`**, you must still allow **inbound TCP** to the chosen **NodePort** (default `32080`) for WebSocket signaling.
  - For full details on STUNner configuration, Gateway/UDPRoute setup, and firewall rules, see `docs/DEPLOYMENT.md`.
- **Security**: default API keys/secrets in `values.yaml` are placeholders and must be overridden for production.

## Model compatibility guidance

This blueprint is validated with:

- **LLM services** exposed via `llm.existingService` or the default `llm` dependency. The application is designed to operate correctly with models **of capability level not lower than Llama 3.3 70B**. Prompts and pipeline configuration have been tuned and tested for this class of models. Using smaller or less capable models may lead to issues such as incorrect or unstable structured output; in such cases, additional prompt or configuration tuning may be necessary.
- **ASR services** that expose an **OpenAI-compatible audio transcription API** and are wired via the bundled `qwen-asr` dependency or `qwen-asr.existingService`. The quality and latency of transcription will depend on the specific ASR model you choose and its configuration.

Production quality depends on model capability and prompt behavior. If you switch to different models or ASR providers, validate transcription quality and generated SOAP consultation output in your target domain.

## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third-party software and materials used within the Solution Blueprints are governed by their respective licenses.
