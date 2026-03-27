<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Helm Deployment
Solution Blueprints are provided as Helm Charts.

The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

## Start Helm template

Set basic variables:
```
export name="aimsb-llm-router"
export namespace="llm-router"
```
## Option 1: Demo Deployment with Self-Hosted LLMs

This option deploys two demonstration LLM pods (requires at least 2 GPUs available on the cluster).
```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
--namespace $namespace \
--set deployDemonstrationLLMs=true \
| kubectl apply -f - -n $namespace
```
## Option 2: Deployment with Existing External LLMs

This approach is suitable if you have deployed LLMs and want to reuse them.
No matter where they are deployed, you can reuse them by following the instructions below.
This is the main operational mode. You have several configuration approaches:

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

The classifiers are implemented using **an LLM with structured output** that:
- Analyzes the text content and context of each query, including conversation history when available
- Uses the LLM's understanding to determine the most appropriate category
- Returns a structured response indicating the predicted class
- Falls back to `Unknown` when the query doesn't clearly match any defined class

For example, when a user asks "Write a function to sort an array", the classifier might determine this is `Code Generation`. When asked "Can you explain quantum computing?", it might classify as `Reasoning`. The classifier leverages the full language understanding capabilities of the underlying LLM to make these decisions.

This flexible approach lets you optimize either for **task-specific expertise** or **computational efficiency** based on your needs.

### Approach A: Configure via values.yaml File

Create or modify `values.yaml`:
```
models:
- name: primary
  base_url: http://primary
  api_key: ""    # optional
  model_name: "" # optional
- name: secondary
  base_url: http://secondary
  api_key: ""    # optional
  model_name: "" # optional

routing:
  rules:
    task_router:
      classifier_path: /classify
      classes:
        Code Generation: secondary
        Summarization: primary
        Unknown: primary

    complexity_router:
      classifier_path: /classify
      classes:
        Hard: secondary
        Middle: secondary
        Easy: primary
        Unknown: primary

classifier:
  llmBackend: secondary
```
Then deploy with:
```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
--namespace $namespace \
-f values.yaml \
| kubectl apply -f - -n $namespace
```
### Approach B: Configure via Command Line Parameters

Set all parameters directly (example command):
```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
--namespace $namespace \
--set models[0].name=primary \
--set models[0].base_url=http://167.99.61.150:8000 \
--set models[1].name=secondary \
--set models[1].base_url=http://167.99.61.150:8000 \
--set models[2].name=third \
--set models[2].base_url=http://167.99.61.150:8000 \
--set models[3].name=four \
--set models[3].base_url=http://167.99.61.150:8000 \
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

**Important notes about parameter `base_url`:**

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

### Approach C: Configure with API Keys and Model Names (Optional)

If your LLMs require authentication, or you need to specify specific models (example command):
```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
--namespace $namespace \
--set models[0].name=primary \
--set models[0].base_url=https://router.huggingface.co \
--set models[0].api_key=exampleapikey \
--set models[0].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set models[1].name=secondary \
--set models[1].base_url=https://router.huggingface.co \
--set models[1].api_key=exampleapikey \
--set models[1].model_name=meta-llama/Llama-3.1-8B-Instruct:novita \
--set routing.rules.task_router.classes.Code\ Generation=secondary \
--set routing.rules.task_router.classes.Summarization=primary \
--set routing.rules.task_router.classes.Unknown=primary \
--set routing.rules.complexity_router.classes.Hard=secondary \
--set routing.rules.complexity_router.classes.Easy=primary \
--set routing.rules.complexity_router.classes.Unknown=primary \
| kubectl apply -f - -n $namespace
```

## Default AIM images and GPU compatibility

When `deployDemonstrationLLMs=true`, the chart deploys two default AIMs:

- `primary.image=amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:0.10.0`
- `secondary.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.10.0`

On newer GPUs, these images may not be the best match and can fail to start or run sub-optimally.
To choose newer AIMs or deploy a different LLMs, override `primary.image` and/or `secondary.image` to compatible images. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
  --namespace $namespace \
  --set deployDemonstrationLLMs=true \
  --set primary.image=amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:<NEWER_TAG> \
  --set secondary.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Connecting to the Service

After deployment, check pod status:
```
kubectl get pods -n $namespace
```
Wait until all pods show ready status `1/1`.

### Option 1: Port Forwarding
To access the web interface, set up port forwarding:
```
kubectl port-forward svc/$name-ui 8080:8008 -n $namespace
```
The UI will then be available at http://localhost:8080

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:

```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
  --namespace $namespace \
  --set http_route.enabled=true \
  # ... (other parameters as needed) ...
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the chart name, release name, and the gateway's hostname. Use this command to produce the URL by querying the hostname from the cluster:
   ```bash
   echo "https://aimsb-llm-router-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
   ```

## Stopping the Deployment

To stop and remove the service, run the same helm template command but with `delete`:

### Use the same helm template command you used for deployment, but with delete
```
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-llm-router \
--namespace $namespace \
# ... (same parameters as deployment) ...
| kubectl delete -f - -n $namespace
```
## Important Notes

- All model names referenced in `routing` and `classifier` sections must exist in the `models` list
- The `api_key` and `model_name` parameters are optional
- When using existing LLMs, ensure your LLM endpoints are accessible from the cluster
- For demo deployment with self-hosted LLMs, ensure at least 2 GPUs are available on the cluster
- Regardless of how you configure the model list, you can specify any number of models.
