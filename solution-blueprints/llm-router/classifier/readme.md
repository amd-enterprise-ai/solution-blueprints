<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Routing Classifier API Documentation

## Overview

The `routing-classifier` service is a FastAPI-based service that classifies conversation messages into predefined categories using a Large Language Model (LLM). It acts as an intelligent classifier that determines the most appropriate category for a given conversation context, enabling dynamic routing decisions in the LLM Router system.

## API Endpoints

### `/classify`
- **Description**: Classifies conversation messages into one of the specified classes.
- **Method**: `POST`
- **Response**: JSON object containing the chosen classification.

#### Request Payload

```
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
- `messages` (array of Message objects, required): Conversation messages to classify, including role and content.
- `classes` (array of strings, optional): List of possible classification categories. Defaults to empty array.

#### Response Format

{
"chosen_class": "Code Generation"
}

**Response Fields:**
- `chosen_class` (string): The selected classification category. Returns "Unknown" if classification fails.

## Configuration

The routing classifier requires the following environment variable:

| Environment Variable  | Description              | Example Value                |
|-----------------------|--------------------------|------------------------------|
| `CLASSIFIER_BASE_URL` | Base URL for the LLM API | `http://129.212.176.80:8000` |

### Setting Environment Variables

export CLASSIFIER_BASE_URL=http://YOUR_MODEL_HOST:8000

## How It Works

### Classification Process

1. **Initialization**: The service automatically fetches the available model name from the LLM API endpoint.
2. **Conversation Reception**: The service receives conversation messages and classification categories.
3. **LLM Query**: It sends a structured request to the configured LLM with system and user prompts.
4. **Response Parsing**: The service parses the LLM's response to extract the classification.
5. **Result Return**: Returns the chosen classification or "Unknown" if parsing fails.

### Internal Logic

The classifier uses the following approach:
1. **Model Discovery**: Automatically detects available model from the LLM API
2. **JSON First**: Attempts to parse the LLM response as JSON
3. **Fallback Parsing**: If JSON parsing fails, attempts `ast.literal_eval`
4. **Default Response**: Returns "Unknown" if all parsing attempts fail

## Error Handling

### Success Cases
- **200 OK**: Successful classification with valid JSON response
- **200 OK with "Unknown"**: Classification attempted but model didn't return valid output

### Error Cases
- **500 Internal Server Error**:
    - Missing required environment variables
    - LLM API request failure
    - Critical parsing errors

### Debug Logging

The service provides detailed debug logging:
- Model discovery process
- Received classification requests
- Raw LLM responses
- Parsing results

## Integration with Router Controller

The routing classifier is typically called by the router-controller service. The integration flow is:

1. Router-controller receives conversation messages
2. Router-controller calls `/classify` endpoint with messages and policy classes
3. Routing classifier returns the classification
4. Router-controller uses classification to select the appropriate LLM
