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

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="Fintech onboarding architecture includes components for capturing live faces and followed by facial detection." src="architecture-diagram-light-scheme.png">
</picture>

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

### How to Use the Service

1. Allow camera access when prompted by the browser.
2. Capture a live face — click the `Start Liveness Check` button. Follow the instructions.
3. If you don’t have a USA driver’s license, you can create a **test version** of one.
   Use this [guide](create-test-driver-licenses.md).
   **Please note**: The test driver licenses you create should be used
   **only for testing this service**.
4. `Upload front side (photo with face)` - select photo of your document containing a face (now
   supporting driver license).
5. `Upload back side (barcode)` - select photo of your document containing a barcode (now supporting
   driver license).
6. Click the `Process Documents` button and view the comparison result of data received from two
   sides of your document.
7. Click the `Run match` button and view the comparison result of the similarity score between the
   live face and the face from the uploaded document.
