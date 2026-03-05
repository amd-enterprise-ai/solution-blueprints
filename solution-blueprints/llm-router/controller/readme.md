<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Router Controller API

## Overview

The `router-controller` is a service responsible for forwarding OpenAI-compatible requests to the appropriate LLMs according to a defined policy. It functions as a proxy that evaluates and classifies user prompts before sending them to the most suitable model.

## API Endpoints Overview

### Configuration Endpoint: `/config`
- **Purpose**: Provides the current configuration details of the router.
- **HTTP Method**: `GET`
- **Response**: Returns a JSON object containing a sanitized version of the router's configuration, including routing_rules and LLM mappings.

### Health Check Endpoint: `/health`
- **Purpose**: Allows clients to verify that the router service is operational.
- **HTTP Method**: `GET`
- **Response**: Returns a JSON object confirming the service status, typically `{ "status": "OK" }`.

### Completion Endpoint: `/v1/chat/completions` or `/completions`
- **Purpose**: Main endpoint for generating chat completions using the appropriate LLM.
- **HTTP Method**: `POST`
- **Request**: Accepts a JSON payload containing the user prompt, messages history, and routing metadata.
- **Response**: Returns a JSON object with the completion produced by the selected LLM according to the routing policy.

## Request Payload

```
{
    "model": "string | empty",
    "messages": [
        {
            "role": "user | system | assistant",
            "content": "string"
        }
    ],
    "llm-router": {
        "policy": "string",
        "routing_strategy": "auto | manual",
        "model": "string | empty"
    },
    "max_tokens": integer,
    "temperature": float,
    "top_p": float,
    "n": integer,
    "stream": boolean,
    "stop": [
        "string"
    ]
}
```

**Fields:**
- **model**: (string) Specifies which LLM model should be used for generating the completion.
- **messages**: (array) Sequence of messages representing the conversation up to this point.
  - **role**: (string) Indicates the author of the message, either `"user"`, `"system"`, or `"assistant"`.
  - **content**: (string) The actual text content of the message.
- **llm-router**: (object) Metadata that guides how the prompt is routed through the LLM Router.
  - **policy**: (string) The routing policy to apply; this field is required.
  - **routing_strategy**: (string) Determines routing behavior, either `"auto"` for automatic classification or `"manual"` to override.
  - **model**: (string) Required if using manual routing; specifies the target model.
- **max_tokens**: (integer) Maximum number of tokens to generate in the response.
- **temperature**: (float) Sampling temperature controlling randomness, range 0–1.
- **top_p**: (float) Nucleus sampling probability, range 0–1.
- **n**: (integer) Number of separate completions to generate per prompt.
- **stream**: (boolean) Whether to stream partial results as they are produced.
- **stop**: (array of strings) Up to four sequences that, when encountered, will halt token generation.

## Configuration

The `router-controller` interacts with the `router-classifier` Inference Server, which hosts the models used to classify incoming prompts.

Router-controller behavior is defined through a YAML configuration file that specifies routing_rules, associated LLMs, and routing strategies.

Multiple routing_rules can be defined within the same [`src/router-controller/config.yaml`](config.yaml) file.

## Routing Strategies

The Router Controller supports two modes of routing:

- **Auto**: Prompts are sent to the router-classifier service for automatic classification, and then routed to the corresponding LLM.
- **Manual**: Prompts are forwarded directly to a specific LLM defined within the selected policy, bypassing automatic classification.

**Configuration Elements:**

Configuration - [`src/router-controller/config.yaml`](config.yaml).
- **routing_rules**: A collection of routing_rules, each defining how prompts are mapped to the appropriate LLMs.
- **rule_name**: Identifier for the rule.
- **classifier_endpoint**: Endpoint of the router-classifier service.
- **models**: List of LLMs (Large Language Models) associated with the policy.
  - **name**: User-defined label for the LLM corresponding to a classification category.
  - **base_url_path**: Base URL for accessing the LLM service.

### Environment Variables

| Environment Variable       | Description                                                     | Example       |
|----------------------------|-----------------------------------------------------------------|---------------|
| `ROUTER_CONTROLLER_CONFIG` | Path to configuration YAML file                                 | `config.yaml` |
| `PORT`                     | Port to run the service on                                      | `8084`        |
| `CLASSIFIER_CONTEXT_MODE`  | Message context mode for classification (`full` or `user_only`) | `user_only`   |
| `CLASSIFIER_CONTEXT_TURNS` | Number of conversation turns to consider                        | `5`           |
