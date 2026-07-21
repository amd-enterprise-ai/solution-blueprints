<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Financial Stock Intelligence (FSI)

## Overview

![FSI UI](./fsi-blueprint-ui.png)

This Solution Blueprint provides a financial analysis workflow through a web interface. It combines real-time stock data, technical indicators, and Large Language Model (LLM) analysis to produce stock insights.

AMD Solution Blueprints are packaged as [Helm charts](https://helm.sh/) for deployment on a Kubernetes cluster. For development or further exploration, the source code is public and available in the [Solution Blueprints GitHub repository](https://github.com/amd-enterprise-ai/solution-blueprints/tree/main/solution-blueprints/fsi).

## Architecture

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The Financial Stock Intelligence application runs inside a single container. It is served by an AIM LLM deployed beside it." src="architecture-diagram-light-scheme.png">
</picture>

The blueprint provides a **Gradio** web application with a financial analysis pipeline and an **AIM** LLM service. By default, the Llama 3.3 70B AIM is deployed for analysis and commentary.

| Component | Role |
|-----------|------|
| Gradio UI | Web interface for entering symbols, date ranges, and reviewing results |
| Analysis pipeline | Market data retrieval, technical indicators, and visualization |
| AIM LLM | AI-generated stock insights (default: Llama 3.3 70B Instruct) |

### Key Features

- Real-time stock data: Live prices and history via Yahoo Finance
- Technical analysis: Simple Moving Average (SMA), Relative Strength Index (RSI), momentum, and price versus SMA comparisons
- AI-powered analysis: Uses Llama 3.3 70B Instruct for intelligent stock insights
- Interactive web interface: Gradio UI for easy interaction
- Historical visualization: Charts and graphs for trend analysis
- News integration: Incorporates relevant financial news for context

## Getting Started

This is a quick start guide on how to deploy the blueprint. For advanced options, such as reusing an existing AIM, providing a Hugging Face token, or overriding storage classes, see [Deploying Solution Blueprints with Helm](https://enterprise-ai.docs.amd.com/en/latest/solution-blueprints/deployment.html) or explore the [advanced deployment guide](./DEPLOYMENT.md).

### Prerequisites

#### System Requirements

This blueprint can be deployed on **AMD Instinct** (default), **AMD EPYC**, and **AMD Radeon**. The blueprint requires the following cluster resources by default, depending on the hardware being used:

| Resource | Instinct | Radeon | EPYC |
|--|--|--|--|
| GPUs | 1 | 1 | — |
| CPUs | 5 CPU cores | 5 CPU cores | 189 CPU cores |
| RAM | 68 Gi | 36 Gi | 132 Gi |

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
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fsi \
  | kubectl apply -f - -n $namespace
```

#### AMD EPYC (CPU)

EPYC runs the model on CPU (`gpus=0`, `bf16`, `AIM_ALLOW_UNOPTIMIZED=true`), sized via `llm.cpus`/`llm.memory`. The default EPYC AIM is a **gated** image, so provide a Hugging Face token through a Secret.

```bash
name="my-deployment"
namespace="my-namespace"
kubectl create namespace $namespace
kubectl create secret generic hf-token --from-literal=hf-token=<YOUR_HF_TOKEN> -n $namespace

helm pull oci://registry-1.docker.io/amdenterpriseai/aimsb-fsi --untar
helm template $name ./aimsb-fsi \
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
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fsi \
  --set global.platform=radeon \
  | kubectl apply -f - -n $namespace
```

<!-- platform-tabs:end -->

### Verify Deployment

To check the status of the deployment, run:

```bash
kubectl get pods -n $namespace
```

Wait until all pods report `Running` and `Ready`.

### Connect to UI

To connect to the UI, port-forward to 8081. The UI will then be available at [http://localhost:8081](http://localhost:8081) in your browser.

```bash
kubectl port-forward services/aimsb-fsi-${name} 8081:80 -n $namespace
```

Once connected, use the application as follows:

1. Enter a stock symbol/ticker
2. Set the date range for the analysis period
3. Click "Analyze Stock" to fetch data, compute indicators, and generate AI commentary
4. Review the results: Technical indicators, charts, AI-generated analysis, and more

### Clean Up

When you are finished, remove the deployed resources using the same deployment command, with `kubectl delete` instead of `kubectl apply`. For example, for Instinct use the following command:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-fsi \
  | kubectl delete -f - -n $namespace
```

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice.

## Third-Party Components

This Solution Blueprint uses multiple third-party components. To see the full set of software and Python dependencies, explore the repository source and dependency files. The table below highlights some of the main components. For further license information, refer to each component's official documentation.

| Component | License |
|---------|---------|
| Gradio | Apache 2.0 |
| LangChain | MIT |
| yfinance | Apache 2.0 |

## Terms of Use

AMD Solution Blueprints are released under the [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third-party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
