<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Whisper Service Chart

A Helm chart designed to deploy the Whisper ASR engine.

## Deployment Guide

Execute the commands below to launch the service. Ensure you define your model path variables first:

Define paths
```console
export MODEL_SOURCE="/data/models"
export TARGET_MODEL="openai/whisper-small"
```

Deploy via Helm
```console
helm install whisper ./whisper
--set global.modelUseHostPath="${MODEL_SOURCE}"
--set ASR_MODEL_PATH="${TARGET_MODEL}"
```

### Testing the Service

You can verify the deployment using `curl` with a sample base64 audio payload:

## Test endpoint (ensure port forwarding is active)

```console
curl -X POST http://localhost:1234/v1/asr
--header 'Content-Type: application/json'
--data '{"audio": "UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA"}'
```

### Configuration Parameters
| Parameter          | Type  | Default                   | Description           |
|:-------------------|:------|:--------------------------|:----------------------|
| `image.repository` | `str` | `amdenterpriseai/whisper` | Docker image source   |
| `service.port`     | `int` | `7066`                    | Internal service port |
