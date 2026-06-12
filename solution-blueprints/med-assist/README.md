<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Med Assist Voice Consultation Blueprint

Helm chart for a realtime med-assist voice consultation workflow. It deploys frontend and agent services with LiveKit
media transport, Qwen ASR transcription, and an LLM backend for consultation report generation.

It helps clinicians document voice consultations by transcribing doctor–patient conversations in real time, generating structured SOAP-style reports for review, and surfacing potential clinical safety issues as categorized alerts (`critical` / `warning` / `info`) during the session.

> **Disclaimer**
> This project is a demonstration application intended for technical evaluation only.
> It does not provide medical advice, diagnosis, or treatment, and must not be used as a substitute for professional medical judgment.

## Quick start (Helm)

### Prerequisites
- Run `./install-prerequisites.sh` to install the **STUNner Operator** (requires `cluster-admin` privileges or rights to create `ClusterRole`, `ClusterRoleBinding`, and CRDs).

### Required LiveKit WebSocket URL
- Set `pythonServices.frontend.env.LIVEKIT_WS_URL` to an externally reachable LiveKit WebSocket URL used by the browser to connect to LiveKit **via STUNner**.
- If this value is empty and `livekit.exposure.mode=nodePort`, the chart auto-generates `LIVEKIT_WS_URL` from `livekit.nodePortService.nodeAddress` and `livekit.nodePortService.nodePort`.
- If this value is empty and `livekit.exposure.mode=httpRoute`, the chart auto-generates `wss://<release.fullname>-livekit.<livekit.httpRoute.hostSuffix>` when `livekit.httpRoute.hostSuffix` is set.
- The agent service can still use in-cluster LiveKit automatically when `pythonServices.agent.env.LIVEKIT_WS_URL` is left empty.
- To use an existing external LiveKit, set `livekit.enabled=false` and pass explicit `pythonServices.frontend.env.LIVEKIT_WS_URL` and `pythonServices.agent.env.LIVEKIT_WS_URL` (plus matching `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` for both services).

More details on how to derive this URL in a STUNner + Gateway/HTTPRoute setup are available in `docs/DEPLOYMENT.md` under the **LiveKit WebSocket URL** section.


```bash
cd solution-blueprints/med-assist
helm dependency build

name="my-deployment"
namespace="my-namespace"
livekit_node_address="<your-ip-node-address>"

helm template $name . \
  --set "livekit.nodePortService.nodeAddress=$livekit_node_address" \
  --set "livekit.nodePortService.nodePort=32080" \
  --namespace $namespace \
  | kubectl apply -f - -n $namespace
```

- By default, LLM and ASR are provided by the `llm` and `qwen-asr` dependencies.
- With **STUNner** integration, media traffic from the browser is routed through the STUNner Gateway. Direct exposure of LiveKit UDP media ports (`50000–60000`) on worker nodes is usually **not required**.
- LiveKit signaling is still exposed in NodePort mode via the parent chart service `"<release>-livekit-nodeport"` (configuration: `livekit.nodePortService.*`).
- In **NodePort** mode you must allow inbound **TCP** access to the configured NodePort (default `32080`) for signaling. See `docs/DEPLOYMENT.md` for details.
- Deployed services: `stunner`, `agent`, `frontend`, `livekit`, plus LLM and ASR services from dependencies.
- Set secrets via `--set`/override file or Kubernetes Secret refs.

## Docs and architecture

- Full docs: `docs/README.md`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture diagram: `docs/architecture-diagram.png`

## Terms of Use

AMD Solution Blueprints are released under the MIT License. Third-party software and materials are governed by their respective licenses.
