<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Routing Classifier API Documentation

## Overview

The `routing-classifier` service is a FastAPI-based service that classifies conversation messages
into predefined categories. It supports two classification approaches: **embedding-based** (using
semantic similarity via an OpenAI-compatible vLLM embedding server) and **LLM-based** (using a language model). The
approach is selected via the `CLASSIFIER_APPROACH` environment variable.

## API Endpoints

### `/classify`

- **Description**: Classifies conversation messages into one of the specified classes.
- **Method**: `POST`
- **Response**: JSON object containing the chosen classification.

#### Request Payload

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Create a quicksort on go language"
    }
  ],
  "classes": [
    "Code Generation",
    "Summarization",
    "Unknown"
  ]
}
```

**Parameters:**

- `messages` (array of Message objects, required): Conversation messages to classify, including role
  and content.
- `classes` (array of strings, optional): List of possible classification categories. If omitted,
  all known classes are used.

#### Response Format

```json
{
  "chosen_class": "Code Generation"
}
```

**Response Fields:**

- `chosen_class` (string): The selected classification category. Returns `"Unknown"` if
  classification fails or confidence is too low.

## Configuration

The required environment variables depend on the selected `CLASSIFIER_APPROACH`.

### Common Variables

| Environment Variable  | Description                                   | Example Value            |
|-----------------------|-----------------------------------------------|--------------------------|
| `CLASSIFIER_APPROACH` | Classification approach: `embedding` or `llm` | `embedding`              |
| `CONTROLLER_URL`      | URL of the router-controller service          | `http://controller:8084` |

### Embedding Approach (`CLASSIFIER_APPROACH=embedding`)

| Environment Variable | Description                                                          | Example Value                          |
|----------------------|----------------------------------------------------------------------|----------------------------------------|
| `EMBEDDING_URL`      | Full URL of the OpenAI-compatible embeddings endpoint (`/v1/embeddings`) | `http://embedding:7997/v1/embeddings` |

### LLM Approach (`CLASSIFIER_APPROACH=llm`)

| Environment Variable    | Description                                            | Example Value       |
|-------------------------|--------------------------------------------------------|---------------------|
| `CLASSIFIER_BASE_URL`   | Base URL for the LLM API                               | `http://llama:8000` |
| `CLASSIFIER_API_KEY`    | API key for the LLM (optional)                         | `sk-...`            |
| `CLASSIFIER_MODEL_NAME` | Model name to use (optional, auto-detected if omitted) | `meta-llama/...`    |

## How It Works

### Embedding Approach

1. **Initialization**: On startup, fetches class names and descriptions from the router-controller
   `/config` endpoint and computes their embeddings via the vLLM embedding server.
2. **Classification**: Encodes the conversation as a query embedding and computes cosine similarity
   against all class embeddings.
3. **Threshold**: If the highest similarity score is below the threshold (0.70 for ≤5 classes, 0.68
   otherwise), returns `"Unknown"`.
4. **Result**: Returns the class with the highest similarity score.

### LLM Approach

1. **Initialization**: Automatically fetches the available model name from the LLM API (unless
   `CLASSIFIER_MODEL_NAME` is set explicitly).
2. **Classification**: Sends a structured prompt with the conversation and class list to the LLM.
3. **Response Parsing**: Attempts JSON parsing first, falls back to `ast.literal_eval`.
4. **Default Response**: Returns `"Unknown"` if all parsing attempts fail.

## Error Handling

### Success Cases

- **200 OK**: Successful classification.
- **200 OK with `"Unknown"`**: Classification attempted but confidence too low (embedding) or model
  returned unparseable output (LLM).

### Error Cases

- **500 Internal Server Error**:
    - Missing required environment variables for the selected approach.
    - LLM API or embedding server request failure.
    - Controller `/config` endpoint unreachable during initialization.

### Debug Logging

The service provides detailed debug logging for both approaches:

- Received messages and classes
- Full dialogue context sent for classification
- Similarity scores per class (embedding approach)
- Raw LLM response and parsed result (LLM approach)
- Selected class and confidence

## Integration with Router Controller

1. Router-controller receives conversation messages.
2. Router-controller calls `/classify` with messages and the list of class names for the active
   routing rule.
3. Classifier returns the chosen class.
4. Router-controller uses the classification to select the appropriate LLM backend.
