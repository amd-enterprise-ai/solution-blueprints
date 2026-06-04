<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AI Blueprint: PDF to Podcast

Helm chart for converting PDFs into podcast-style audio. It deploys API, agent, PDF ingest, TTS, and LLM-backed services.

## Quick start (Helm)

Both the LLM and TTS services are deployed automatically via subchart dependencies (`aimchart-llm` and `aimchart-qwen-tts`). The environment variables `APP_LLM_URL` and `APP_TTS_BASE_URL` are auto-configured from the subchart service URLs.

```bash
cd solution-blueprints/pdf-to-podcast
helm dependency build

name="my-deployment"
namespace="my-namespace"
helm template $name . \
  | kubectl apply -f - -n $namespace
```

- LLM is provided by the `aimchart-llm` dependency; override with `llm.existingService` if you already have an LLM endpoint.
- TTS is provided by the `aimchart-qwen-tts` dependency; override with `qwen-tts.existingService` if you already have an OpenAI-compatible TTS endpoint.
- Services: `app` (API service on port 8000), `celery-worker` (background tasks), `frontend` (UI on port 7860), `redis` (task queue), LLM service, and TTS service. Ports/env are in `values.yaml`.
- Set secrets via `--set`/override file or Kubernetes Secret refs.

## Docs and architecture

- Full docs: `docs/README.md`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture diagram: `docs/architecture-diagram.png`

## Terms of Use

AMD Solution Blueprints are released under the MIT License. Third-party software and materials are governed by their respective licenses.
