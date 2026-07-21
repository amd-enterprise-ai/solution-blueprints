<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Document Summarization

## Overview

![Document Summarization UI](assets/img/document-summarization-blueprint-ui.png)

The Document Summarization (DocSum) Solution Blueprint uses LLMs to generate summaries from varied document types. It can process and summarize PDFs, DOCX files and plain text, as well as multimedia files (both audio and video), across a variety of domains such as customer service, scientific research and legal text.

AMD Solution Blueprints are packaged as [Helm charts](https://helm.sh/) for deployment on a Kubernetes cluster. For development or further exploration, the source code is public and available in the [Solution Blueprints GitHub repository](https://github.com/amd-enterprise-ai/solution-blueprints/tree/main/solution-blueprints/document-summarization).

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="assets/img/architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="assets/img/architecture-diagram-dark-scheme.png">
  <img alt="Document Summarization architecture on AMD AIM: UI, DocSum MegaService, Whisper ASR, and LLM backends."
  src="assets/img/architecture-diagram-light-scheme.png">
</picture>

| Component | Role |
|-----------|------|
| User Interface | Web interface for uploads, URLs, and viewing summaries |
| Backend API | DOCSUM backend integration between components |
| Whisper | Automatic transcription for audio and video inputs |
| AIM LLM | Summarization and language understanding (default: Llama 3.3 70B Instruct) |

### Key Features

- Multi-format support: PDF, DOCX, text, audio, and video
- Automatic transcription: Whisper-based speech-to-text for multimedia files
- LLM-powered summarization: Deploy with AIM
- Microservices Architecture: Modular design with independent, scalable components

## Getting Started

This is a quick start guide on how to deploy the blueprint. For advanced options, such as reusing an existing AIM, providing a Hugging Face token, or overriding storage classes, see [Deploying Solution Blueprints with Helm](https://enterprise-ai.docs.amd.com/en/latest/solution-blueprints/deployment.html) or explore the [advanced deployment guide](./DEPLOYMENT.md).

### Prerequisites

#### System Requirements

This blueprint can be deployed on **AMD Instinct** (default), **AMD EPYC**, and **AMD Radeon**. The blueprint requires the following cluster resources by default, depending on the hardware being used:

| Resource | Instinct | Radeon | EPYC |
|--|--|--|--|
| GPUs | 1 | 1 | — |
| CPUs | 5 CPU cores | 5 CPU cores | 189 CPU cores |
| RAM | 65 Gi | 33 Gi | 129 Gi |

To deploy to the Kubernetes cluster, ensure the following prerequisites are met:

- [kubectl](https://kubernetes.io/docs/tasks/tools/): Installed and configured to communicate with the cluster
- [Helm](https://helm.sh/docs/intro/install/) 3.17 or higher: Installed on your local machine

### Deployment

For advanced deployment options, explore the [advanced deployment guide](./DEPLOYMENT.md). Solution Blueprints are packaged as OCI-compliant Helm charts in the Docker Hub registry and can be deployed to a Kubernetes cluster with a single command. Define the `name` (deployment name) and the `namespace` (Kubernetes namespace), then pipe the output of `helm template` to `kubectl apply -f -`.

Find the deployment command below.

Note: You can create a namespace using `kubectl create namespace <my-namespace>`.

<!-- platform-tabs:start -->

#### AMD Instinct (GPU, default)

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-docsum \
  | kubectl apply -f - -n $namespace
```

#### AMD EPYC (CPU)

EPYC runs the model on CPU (`gpus=0`, `bf16`, `AIM_ALLOW_UNOPTIMIZED=true`), sized via `llm.cpus`/`llm.memory`. The default EPYC AIM is a **gated** image, so provide a Hugging Face token through a Secret.

```bash
name="my-deployment"
namespace="my-namespace"
kubectl create namespace $namespace
kubectl create secret generic hf-token --from-literal=hf-token=<YOUR_HF_TOKEN> -n $namespace

helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-docsum --untar
helm template $name ./aimsb-docsum \
  --set global.platform=epyc \
  --set llm.cpus=188 \
  --set llm.memory=128 \
  --set llm.env_vars.HF_TOKEN.name=hf-token \
  --set llm.env_vars.HF_TOKEN.key=hf-token \
  | kubectl apply -f - -n $namespace
```

> **Performance note**: On multi-socket EPYC nodes, configure the kubelet for NUMA alignment (CPU Manager `static`, Topology Manager `single-numa-node`, Memory Manager `Static`); otherwise the LLM's CPUs and memory can land on different NUMA nodes and vLLM runs effectively single-threaded.

#### AMD Radeon (GPU)

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-docsum \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

<!-- platform-tabs:end -->

### Verify Deployment

To check the status of the deployment, run:

```bash
kubectl get pods -n $namespace
```

Wait until all pods report `Running` and `Ready`. Summarization requires the LLM (and Whisper for media paths) to be up; the default AIM may take several minutes to start.

### Connect to UI

To connect to the UI, port-forward to 5173. The UI is then available at [http://localhost:5173](http://localhost:5173) in your browser.

```bash
kubectl port-forward services/aimsb-docsum-${name}-ui 5173:5173 -n $namespace
```

Once connected, use the application as follows:

1. Choose a source: Upload one or more supported files (Text, Documents, Audio, or Video)
2. Click "Generate Summary" to submit the request and wait for the summarization to finish
3. Review the generated summary in the UI

### Clean Up

When you are finished, remove the deployed resources using the same deployment command, with `kubectl delete` instead of `kubectl apply`. For example, for Instinct use the following command:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-docsum \
  | kubectl delete -f - -n $namespace
```

## Third-Party Components

This Solution Blueprint uses multiple third-party components. To see the full set of software and Python dependencies, explore the repository source and dependency files. For further license information, refer to each component's official documentation.

## Terms of Use

AMD Solution Blueprints are released under the [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
