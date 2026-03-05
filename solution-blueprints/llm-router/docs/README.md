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

For example, under a task classification policy, user prompts are analyzed, categorized, and seamlessly sent to the most appropriate model for execution.

| User Prompt                                                                                                                                                                                                          | Task Classification | Route To        |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------|-----------------|
| "Create a quicksort on go language"                                                                                                                                                                                  | Code Generation     | secondary-llm   |
| "Based on these three facts: First, water boils at 100°C. Second, ice melts at 0°C. Third, evaporation occurs at various temperatures. What general conclusion can be drawn about states of matter and temperature?" | Summarization       | primary-llm     |
| "Hello"                                                                                                                                                                                                              | Unknown             | primary-llm     |


## Software Components

The LLM Router is composed of three main components:
- **Router Controller** — a proxy-like service responsible for routing OpenAI-compatible requests.
- **Router Classifier** — a service that analyzes and classifies the user’s prompt using a general-purpose LLM. This model is prompted to behave as a classifier and return a structured output that assigns the prompt to the appropriate policy category.
- **Downstream LLMs** — the target LLMs that ultimately receive the prompt.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The LLM Router architecture consists of the UI, Controller, and Classifier together with several AIM LLMs." src="architecture-diagram-light-scheme.png">
</picture>

### Policies

The configuration file defines the available routing policies. In the default setup, a prompt can be evaluated using either the `task_router` policy or the `complexity_router` policy.

The `task_router` relies on a router-classifier service deployed at `http://router-classifier:8010/classify`. This service uses an LLM to categorize prompts according to the type of task they represent:
- Code Generation
- Summarization
- Unknown

The `complexity_router` also uses a router-classifier service deployed at `http://router-classifier:8010/classify`. In this case, the LLM classifies prompts based on their perceived complexity:
- Hard
- Middle
- Easy
- Unknown

### LLMs

The `llms` configuration determines how classified prompts are routed to different LLM backends and is defined in the Helm `values.yml` file.

Example configuration from `values.yml`:
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

### Using the Router

The LLM Router exposes an OpenAI-compatible API and can be used as a drop-in replacement for existing OpenAI-based applications. Requests keep the standard OpenAI structure, while the router transparently handles model selection based on configured routing logic.

The only required extension is the inclusion of `llm-router` metadata in the request body. This metadata controls how the request is classified and routed:

- **policy**: defines which classification policy should be applied (by default, `task_router` or `complexity_router`).
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
