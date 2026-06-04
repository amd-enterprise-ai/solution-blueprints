<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

## Overview

Finding the right Large Language Model (LLM) for a task can be difficult. While the perfect model
would be accurate, fast, and inexpensive, real-world systems often force a choice between these
competing factors.

This design presents a routing system that automates this choice. When a user submits a prompt, the
system follows this process:

1. **Applies a Routing Policy**: It uses a defined strategy, such as classifying the prompt by its
   task type or complexity level.
2. **Classifies the Prompt**: The system analyzes the incoming prompt and assigns it to the correct
   category from the policy. Two classification approaches are supported: embedding-based and
   LLM-based (described below).
3. **Routes to the Optimal LLM**: Based on this classification, the system automatically proxies the
   original prompt to the LLM backend best suited for that specific category—whether optimized for
   accuracy, speed, or cost.

For example, under a task classification policy, user prompts are analyzed, categorized, and
seamlessly sent to the most appropriate model for execution.

| User Prompt                                                                                                                                                                                                          | Task Classification | Route To      |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------|---------------|
| "Create a quicksort on go language"                                                                                                                                                                                  | Code Generation     | secondary-llm |
| "Based on these three facts: First, water boils at 100°C. Second, ice melts at 0°C. Third, evaporation occurs at various temperatures. What general conclusion can be drawn about states of matter and temperature?" | Summarization       | primary-llm   |
| "Hello"                                                                                                                                                                                                              | Unknown             | primary-llm   |

## Software Components

The LLM Router is composed of three main components:

- **Router Controller** — a proxy-like service responsible for routing OpenAI-compatible requests.
- **Router Classifier** — a service that analyzes and classifies the user's prompt. Supports two
  classification approaches: embedding-based and LLM-based.
- **Downstream LLMs** — the target LLMs that ultimately receive the prompt.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The LLM Router architecture consists of the UI, Controller, and Classifier together with several AIM LLMs." src="architecture-diagram-light-scheme.png">
</picture>

## Classification Approaches

The Router Classifier supports two modes of operation, selected via `embedding.enabled` in
`values.yaml`.

### Embedding-based Classification
values: `embedding.enabled: true`

The classifier loads class descriptions from the router-controller config, computes their embeddings
using the [Infinity](https://github.com/michaelfeil/infinity) embedding server with the
`intfloat/multilingual-e5-large-instruct` model, and classifies each incoming prompt by finding the
class with the highest cosine similarity to the query embedding.

**Pros:**

- Fast and lightweight — no LLM inference required for classification.
- Deterministic results.
- Works well even with smaller, less capable LLM backends.

**Cons:**

- Quality depends on how well the class descriptions are written.
- Requires an additional embedding service to be deployed.

### LLM-based Classification
values: `embedding.enabled: false`

The classifier sends the conversation and the list of class names to a configured LLM backend,
instructing it to return a structured JSON response with the chosen class.

**Pros:**

- Can handle nuanced or ambiguous prompts better in some cases.
- No additional embedding service required.

**Cons:**

- Slower — adds an extra LLM inference call to every request.
- Quality depends on the capability of the classifier LLM.
- Non-deterministic — results may vary between runs.

**Recommendation**: Based on practical experience, the **embedding-based approach** performs better
overall. It is faster, more consistent, and produces reliable results when class descriptions are
written clearly. The LLM-based approach may occasionally handle edge cases better, but the added
latency and non-determinism make it less suitable for production routing.

### Policies

The configuration file defines the available routing policies. Each class now includes both a
`backend` (which LLM to route to) and a `description` (used by the embedding classifier to match
incoming prompts).

The `task_router` categorizes prompts by task type:

- **Code Generation** → secondary LLM
- **Summarization** → primary LLM
- **Unknown** → primary LLM

The `complexity_router` categorizes prompts by complexity:

- **Hard** → secondary LLM
- **Middle** → secondary LLM
- **Easy** → primary LLM
- **Unknown** → primary LLM

### LLMs

The `models` configuration in `values.yaml` defines available LLM backends. Each class in a routing
rule references a backend by name.

Example configuration from `values.yaml`:

```yaml
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

### Using the Router

The LLM Router exposes an OpenAI-compatible API and can be used as a drop-in replacement for
existing OpenAI-based applications. Requests keep the standard OpenAI structure, while the router
transparently handles model selection based on configured routing logic.

The only required extension is the inclusion of `llm-router` metadata in the request body. This
metadata controls how the request is classified and routed:

- **policy**: defines which classification policy should be applied (by default, `task_router` or
  `complexity_router`).
- **routing_strategy**: specifies how routing decisions are made.
    - `auto` delegates classification to the router-classifier service.
    - `manual` skips classification and allows the client to explicitly control routing behavior.

#### Request format

```
POST /v1/chat/completions
Content-Type: application/json
Accept: application/json
{
  "model": "string | empty",
  "messages": [
    {
      "role": "user | system | assistant",
      "content": "string"
    }
  ],
  "max_tokens": integer,
  "stream": boolean,
  "llm-router": {
    "policy": "string",
    "routing_strategy": "auto | manual",
    "model": "string | empty"
  }
}
```
