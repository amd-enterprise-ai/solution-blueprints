<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Report Generation Engine

AI-powered report generation with web research capabilities.

First set the name of your deployment and the namespace.

```bash
name="rge"
namespace="rge"
```

Then build the dependencies:

```bash
helm dependency build
```

Use `helm template` to assemble the template, and pass the output to `kubectl apply` to start it up on kubernetes:

```bash
helm template $name . \
  --set config.tavily.apiKey=tvly-your-key-here \
  | kubectl apply -f - -n $namespace
```

When the service has started, port-forward 8501 to be able to access the UI. The UI will then be available at <http://localhost:8501>

```bash
kubectl port-forward services/aimsb-report-generation-engine-$name 8501:8501 -n $namespace
```

Report generation will work only when the LLM service is also up and running. Note that the default model used is large and can take ~10 minutes to start.
