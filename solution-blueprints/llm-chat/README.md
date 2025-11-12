<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# LLM-Chat

Get a feel for your LLM in a safe sandbox. Explore prompting techniques, valiate outputs, and understand model behavior before embedding LLMs into critical enterprise workflows.

## Components
- AIM LLM:
    - A full, optimized LLM deployment
    - See the [library chart](../../library-charts/aim-llm/README.md) for its documentation
- OpenWebUI:
    - An open source AI platform

## Deploying

First set the name of your deployment, choose whatever you wish.
```bash
name=testing-llm-chat
```
Then run
```bash
helm dependency build .
helm template $name . \
    | kubectl apply -f -
```
