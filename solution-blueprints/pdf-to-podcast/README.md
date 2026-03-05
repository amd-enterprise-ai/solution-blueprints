<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AI Blueprint: PDF to Podcast

Helm chart for converting PDFs into podcast-style audio. It deploys API, agent, PDF ingest, TTS, and LLM-backed services.

## Quick start (Helm)

### ElevenLabs API key

- Sign up at https://elevenlabs.io/ (new accounts typically receive ~10,000 free credits, ~10 minutes of TTS audio).
- Create an API key with access to TTS and set it in `pythonServices.app.env.APP_ELEVENLABS_API_KEY`.
- If you only need the no‑TTS mode, you can omit the ElevenLabs API key entirely.

```bash
cd solution-blueprints/pdf-to-podcast
helm dependency build

name="my-deployment"
namespace="my-namespace"
helm template $name . \
  --set pythonServices.app.env.APP_ELEVENLABS_API_KEY="<your_11labs_key>" \
  | kubectl apply -f - -n $namespace
```

- LLM is provided by the `aimchart-llm` dependency; override with `llm.existingService` if you already have an LLM endpoint.
- Services: `app` (API service on port 8000), `celery-worker` (background tasks), `frontend` (UI on port 7860), `redis` (task queue), and LLM service. Ports/env are in `values.yaml`.
- Set secrets via `--set`/override file or Kubernetes Secret refs.

## Docs and architecture

- Full docs: `docs/README.md`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture diagram: `docs/architecture-diagram.png`

## Terms of Use

AMD Solution Blueprints are released under the MIT License. Third-party software and materials are governed by their respective licenses.
