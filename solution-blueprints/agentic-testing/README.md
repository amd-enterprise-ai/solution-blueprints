<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic Testing

AI-powered UI testing using an LLM agent with Playwright MCP for browser automation.

## Starting the service

First set the name of your deployment and the namespace.

```bash
name="my-deployment"
namespace="my-namespace"
```

Then build the dependencies:

```bash
helm dependency build
```

Use `helm template` to assemble the template, and pass the output to `kubectl apply` to start it up on kubernetes:

```bash
helm template $name . | kubectl apply -f - -n $namespace
```

## Accessing the UI

**Option 1: Port-forward** (for local access)

```bash
kubectl port-forward services/aimsb-agentic-testing-$name-ui 8501:8501 -n $namespace
```

The UI will be available at <http://localhost:8501>

**Option 2: HTTPRoute** (for external access via Gateway API)

Deploy with HTTPRoute enabled:

```bash
helm template $name . --set ui.httpRoute.enabled=true | kubectl apply -f - -n $namespace
```

Enter your test specifications in Gherkin format (Given-When-Then syntax) in the UI and run tests. The UI displays real-time execution logs and generates pytest-playwright code from successful runs.

Tests will work only when the LLM service is also up and running. Note that the default model used is large and can take ~10 minutes to start.
