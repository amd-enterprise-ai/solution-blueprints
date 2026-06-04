<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

## Overview

Finding the right Large Language Model (LLM) for a task can be difficult. While the perfect model would be accurate, fast, and inexpensive, real-world systems often force a choice between these competing factors.

This design presents a routing system that automates this choice. When a user submits a prompt, the system follows this process:

1.  Applies a Routing Policy: It uses a defined strategy, such as classifying the prompt by its task type or complexity level.
2.  Classifies the Prompt: Instead of a pre-trained classifier, it uses a standard, general-purpose LLM. This LLM is instructed to act as a classifier and provide a structured output that tags the incoming prompt with the correct category from the policy.
3.  Routes to the Optimal LLM: Based on this classification, the system automatically proxies the original prompt to the LLM backend best suited for that specific category—whether optimized for accuracy, speed, or cost.

# Quickstart Guide

This blueprint supports two usage approaches:
1. **Deployment with existing LLMs** (main operational mode) - connects to your pre-existing LLM services
2. **Demo deployment with self-hosted LLMs** - deploys two demonstration LLM pods (for testing purposes)

## Prerequisites

- `helm` and `kubectl` installed on your machine
- **For demo deployment with self-hosted LLMs**: At least 2 GPUs available on the cluster
- **For deployment with existing LLMs**: Minimal requirements, just access to your LLM endpoints

## Option 1: Deploying with Self-Hosted LLMs (Demo Scenario)

### 1. Start Helm Template
Run the following command to deploy with demonstration LLM pods:
```
export name="aimsb-llm-router"
export namespace="llm-router"

helm template $name . \
--namespace $namespace \
--set deployDemonstrationLLMs=true \
| kubectl apply -f - -n $namespace
```
### 2. Check Pod Status
Verify that all pods are running:
```
kubectl get pods -n $namespace
```
Wait until all pods show ready status `1/1`.

### 3. Access the Web Interface
Set up port forwarding to access the UI:
```
kubectl port-forward svc/aimsb-llm-router-ui 8080:8008 -n $namespace
```
The web interface will be available at http://localhost:8080

### 4. Stop the Deployment
When finished, clean up the deployment:
```
helm template $name . \
--namespace $namespace \
--set deployDemonstrationLLMs=true \
| kubectl delete -f - -n $namespace
```
## Option 2: Deploying with Existing LLMs (Main Scenario)

This approach is suitable if you have deployed LLMs and want to reuse them.
When using existing LLMs, ensure your LLM endpoints are accessible from the cluster.

### Understanding Routing Rules

The routing system uses a **configurable classification approach** to direct requests to the most appropriate LLM. You can choose between two classification strategies in the UI:

#### Option 1: Task-Based Routing
When **Task-Based** routing is selected, the system analyzes the user's query to understand the **intended task type**. Common task classes include:
- `Code Generation` - Writing new code
- `Summarization` - Condensing long texts
- `Reasoning` - Logical problem-solving
- `Creative Writing` - Generating stories or marketing copy
- And many others...

#### Option 2: Complexity-Based Routing
When **Complexity-Based** routing is selected, the system evaluates the **complexity level** of the request:
- `Easy` - Simple, straightforward tasks
- `Middle` - Moderately complex requests
- `Hard` - Complex reasoning or long-form generation
- `Trivial` - Very simple queries

### Classifier Interpretation

The classifier supports two classification approaches, selected via `embedding.enabled`:

#### Embedding-based Classification
(values: `embedding.enabled: true`, default)

Uses the `intfloat/multilingual-e5-large-instruct` model via the Infinity embedding server. Each class has a `description` field — the classifier computes semantic similarity between the incoming prompt and class descriptions, routing to the closest match. This approach is **faster, deterministic, and recommended for production use**.

#### LLM-based Classification
(values: `embedding.enabled: false`)

Uses a configured LLM backend to classify the prompt. The LLM receives the conversation and the list of class names, and returns a structured JSON response with the chosen class. This approach requires no additional embedding service but adds an extra LLM inference call to every request.

Both approaches fall back to `Unknown` when the query doesn't clearly match any defined class.

### 1. Configure Your LLMs
You have two configuration options:

#### Option A: Configure via values.yaml
Create or modify `values.yaml`:
```
models:
  - name: primary
    base_url: http://primary
    api_key: ""    # optional
    api_key_secret_ref: {} # optional, e.g. { name: llm-api-keys, key: primary }
    model_name: "" # optional
  - name: secondary
    base_url: http://secondary
    api_key: ""    # optional
    api_key_secret_ref: {} # optional, e.g. { name: llm-api-keys, key: secondary }
    model_name: "" # optional

routing:
  rules:
    task_router:
      classifier_path: /classify
      classes:
        Code Generation:
          backend: secondary
          description: "Any request to create, write, generate, implement or provide code in any programming language, algorithm implementations, scripts, functions, or code examples."
        Summarization:
          backend: primary
          description: "Tasks related to summarizing text, condensing articles, conversations, documents, providing key points or brief overviews."
        Unknown:
          backend: primary
          description: "Requests that are completely unclear, off-topic, spam, or do not match ANY of the defined categories at all."

    complexity_router:
      classifier_path: /classify
      classes:
        Hard:
          backend: secondary
          description: "High-effort tasks: algorithms, complex math, deep multi-step reasoning, code writing, advanced technical topics."
        Middle:
          backend: secondary
          description: "Medium effort tasks: short explanations, standard how-to questions, everyday problem solving, moderate knowledge recall."
        Easy:
          backend: primary
          description: "Very low-effort interactions: greetings, simple yes/no questions, basic facts, casual chat."
        Unknown:
          backend: primary
          description: "Requests that are completely unclear, off-topic, spam, or do not match ANY of the defined categories at all."

classifier:
  llmBackend: secondary  # used only when embedding.enabled: false

embedding:
  enabled: true  # true = embedding approach, false = LLM approach
```
**Important**: All model names referenced in `routing` and `classifier` sections must exist in the `models` list.
The router service will validate that all model names referenced in routing rules exist in the configured models list.
For each model, you can provide either `api_key` directly or `api_key_secret_ref` to read from a Kubernetes Secret.
If both are set, `api_key` is used.
`apiKeySecretRef` is also accepted as an alias for `api_key_secret_ref`.

Then deploy with:
```
export name="aimsb-llm-router"
export namespace="llm-router"

helm template $name . \
--namespace $namespace \
-f values.yaml \
| kubectl apply -f - -n $namespace
```
#### Option B: Configure via Command Line Parameters

You can set all parameters directly using `--set` flags in the `helm template` command.

**Important notes about `base_url`:**

- `base_url` is **only the base address of the model service**, without any API path suffix
  Correct examples:
    - `http://167.99.61.150:8000`
    - `http://llama3-70b-instruct`
    - `http://my-model.default.svc.cluster.local`
    - `http://vllm-backend.llm-router.svc.cluster.local:8000`

- **Do NOT add** `/v1`, `/v1/chat/completions`, `/api`, `/openai` etc. at the end
  The router automatically appends the correct path: `$base_url/v1/chat/completions`
- The service at this address **must** provide an **OpenAI-compatible API**
  (it should accept POST requests at `/v1/chat/completions`)

- **About the port**
    - If the model service listens on the **default http port 80** → you can omit the port entirely
      Example: `http://my-model-service`
    - If it uses a **non-standard port** (most often 8000 for vLLM, llama.cpp, Ollama with custom port, etc.) → you **must** specify the port
      Example: `http://my-model-service:8000`
    - The most common case inside Kubernetes: when models are running in the same cluster → use the **Kubernetes service name** (without external IP)

**Example 1: Models are running inside the same Kubernetes cluster**

```
export name="aimsb-llm-router"
export namespace="llm-router"

helm template $name . \
  --namespace $namespace \
  --set embedding.enabled=false \
  --set models[0].name=primary \
  --set models[0].base_url=http://llama3-8b-instruct \
  --set models[1].name=secondary \
  --set models[1].base_url=http://deepseek-coder-v2-16b \
  --set models[2].name=third \
  --set models[2].base_url=http://qwen2.5-72b-instruct \
  --set models[3].name=four \
  --set models[3].base_url=http://gemma2-27b-it \
  \
  --set routing.rules.task_router.classes.Code\ Generation=secondary \
  --set routing.rules.task_router.classes.Code\ Review=secondary \
  --set routing.rules.task_router.classes.Refactoring=secondary \
  --set routing.rules.task_router.classes.Summarization=primary \
  --set routing.rules.task_router.classes.Documentation=primary \
  --set routing.rules.task_router.classes.Reasoning=third \
  --set routing.rules.task_router.classes.Logical\ Analysis=third \
  --set routing.rules.task_router.classes.Planning=third \
  --set routing.rules.task_router.classes.Decision\ Making=third \
  --set routing.rules.task_router.classes.Creative\ Writing=four \
  --set routing.rules.task_router.classes.Brainstorming=four \
  --set routing.rules.task_router.classes.Marketing\ Text=four \
  --set routing.rules.task_router.classes.Unknown=primary \
  \
  --set routing.rules.complexity_router.classes.Hard=secondary \
  --set routing.rules.complexity_router.classes.Middle=secondary \
  --set routing.rules.complexity_router.classes.Easy=primary \
  --set routing.rules.complexity_router.classes.Trivial=third \
  --set routing.rules.complexity_router.classes.Unknown=primary \
  | kubectl apply -f - -n $namespace
```

**Example 2: Models are running outside the cluster (external IP / cloud endpoint)**
```
export name="aimsb-llm-router"
export namespace="llm-router"

helm template $name . \
  --namespace $namespace \
  --set embedding.enabled=false \
  --set models[0].name=primary \
  --set models[0].base_url=http://167.99.61.150:8000 \
  --set models[1].name=secondary \
  --set models[1].base_url=http://another-provider.com:8080 \
  --set models[2].name=third \
  --set models[2].base_url=https://api.deepseek.com \
  \
  --set routing.rules.task_router.classes.Code\ Generation=secondary \
  --set routing.rules.task_router.classes.Code\ Review=secondary \
  --set routing.rules.task_router.classes.Refactoring=secondary \
  --set routing.rules.task_router.classes.Summarization=primary \
  --set routing.rules.task_router.classes.Documentation=primary \
  --set routing.rules.task_router.classes.Reasoning=third \
  --set routing.rules.task_router.classes.Logical\ Analysis=third \
  --set routing.rules.task_router.classes.Planning=third \
  --set routing.rules.task_router.classes.Decision\ Making=third \
  --set routing.rules.task_router.classes.Creative\ Writing=four \
  --set routing.rules.task_router.classes.Brainstorming=four \
  --set routing.rules.task_router.classes.Marketing\ Text=four \
  --set routing.rules.task_router.classes.Unknown=primary \
  \
  --set routing.rules.complexity_router.classes.Hard=secondary \
  --set routing.rules.complexity_router.classes.Middle=secondary \
  --set routing.rules.complexity_router.classes.Easy=primary \
  --set routing.rules.complexity_router.classes.Trivial=third \
  --set routing.rules.complexity_router.classes.Unknown=primary \
  | kubectl apply -f - -n $namespace
```
If your models are running inside the same Kubernetes cluster, in most cases you only need to use the service name (with :8000 if the port is non-standard).
Check the router logs if something doesn't work — they usually show exactly which URL is being called and what error is received.

#### Optional: Adding API Keys and Model Names
If your LLMs require authentication, or you need to specify model names (when multiple models are available at the same URL), add `api_key` and `model_name` parameters (example command):
```
export name="aimsb-llm-router"
export namespace="llm-router"

helm template $name . \
--namespace $namespace \
--set embedding.enabled=false \
--set models[0].name=primary \
--set models[0].base_url=https://router.huggingface.co \
--set models[0].api_key=exampleapikey \
--set models[0].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set models[1].name=secondary \
--set models[1].base_url=https://router.huggingface.co \
--set models[1].api_key=exampleapikey \
--set models[1].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set models[2].name=third \
--set models[2].base_url=https://router.huggingface.co \
--set models[2].api_key=exampleapikey \
--set models[2].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set models[3].name=four \
--set models[3].base_url=https://router.huggingface.co \
--set models[3].api_key=exampleapikey \
--set models[3].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set routing.rules.task_router.classes.Code\ Generation=secondary \
--set routing.rules.task_router.classes.Code\ Review=secondary \
--set routing.rules.task_router.classes.Refactoring=secondary \
--set routing.rules.task_router.classes.Summarization=primary \
--set routing.rules.task_router.classes.Documentation=primary \
--set routing.rules.task_router.classes.Reasoning=third \
--set routing.rules.task_router.classes.Logical\ Analysis=third \
--set routing.rules.task_router.classes.Planning=third \
--set routing.rules.task_router.classes.Decision\ Making=third \
--set routing.rules.task_router.classes.Creative\ Writing=four \
--set routing.rules.task_router.classes.Brainstorming=four \
--set routing.rules.task_router.classes.Marketing\ Text=four \
--set routing.rules.task_router.classes.Unknown=primary \
--set routing.rules.complexity_router.classes.Hard=secondary \
--set routing.rules.complexity_router.classes.Middle=secondary \
--set routing.rules.complexity_router.classes.Easy=primary \
--set routing.rules.complexity_router.classes.Trivial=third \
--set routing.rules.complexity_router.classes.Unknown=primary \
| kubectl apply -f - -n $namespace
```
> By default `embedding.enabled=true` (embedding-based classification). Set `embedding.enabled=false` to use LLM-based classification instead. When using LLM-based classification, `classifier.llmBackend` must reference a valid model from the `models` list.
The `api_key` and `model_name` parameters are optional. If not specified, they will not be used in LLM requests.
### 2. Check Pod Status
Verify deployment:
```
kubectl get pods -n $namespace
```
Wait until all pods show ready status `1/1`.

### 3. Access the Web Interface
Set up port forwarding:
```
kubectl port-forward svc/$name-ui 8080:8008 -n $namespace
```
Access the web interface at http://localhost:8080

### 4. Stop the Deployment
To stop and remove the service, run the same helm template command with `delete`:

### Use the same helm template command you used for deployment, but with delete
```
helm template $name . \
--namespace $namespace \
# ... (same parameters as deployment) ...
| kubectl delete -f - -n $namespace
```
