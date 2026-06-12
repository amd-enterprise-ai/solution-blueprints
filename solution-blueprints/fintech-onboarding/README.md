<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# FinTech Service

A lightweight **KYC (Know Your Customer)** prototype for face-based identity verification.
This service compares a live face captured via webcam with a face extracted from an uploaded ID
document.

---

## Overview

It uses [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
for face detection and
[SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) for
face recognition and embedding extraction, both
from [opencv_zoo](https://github.com/opencv/opencv_zoo).

The system is containerized using Docker and consists of two services:

- **Web frontend** — user interface for capturing live faces and uploading documents
- **Backend** — performs face detection and similarity comparison (include models, see scheme)
- **BFF (Backend For Frontend)** — mediator for more useful using infrastructure

> ⚠️ **Restrictions:**
> The backend uses YuNet (face detection) and SFace (face recognition) models, which are deployed
> inside the Backend. The models are downloaded on first startup, which may cause slower initial
> launch times.
---

## Model Notes

The service uses **YuNet** (face detection) and **SFace** (face recognition) from
[opencv_zoo](https://github.com/opencv/opencv_zoo). Both models are licensed for commercial use
(MIT and Apache 2.0).

> ⚠️ **Known restrictions:**
> - SFace achieves competitive accuracy on standard benchmarks (LFW ~99.55%).
> - **Robustness to occlusions** (glasses, hijab, medical masks) is not formally documented for
    SFace; community reports indicate a drop in similarity scores under strong facial occlusions,
    especially around the eyes and lower face.

---

## GPU Support (AMD ROCm)

The service requires **at least 1 AMD GPU** to run. All necessary parameters will be set
automatically.
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

### How to Use the Service

1. Allow camera access when prompted by the browser.
2. Capture a live face — click the `Start Liveness Check` button. Follow the instructions.
3. If you don’t have a USA driver’s license, you can create a **test version** of one.
   Use this [guide](docs/create-test-driver-licenses.md).
   **Please note**: The test driver licenses you create should be used
   **only for testing this service**.
4. `Upload front side (photo with face)` - select photo of your document containing a face (now
   supporting driver license).
5. `Upload back side (barcode)` - select photo of your document containing a barcode (now supporting
   driver license).
6. Click the `Process Documents` button and view the comparison result of data received from two
   sides of your document.
7. Click the `Run match` button and view the comparison result of the similarity score between the
   live face and the face from the uploaded documen
