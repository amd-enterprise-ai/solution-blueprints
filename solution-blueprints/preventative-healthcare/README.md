<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Preventative Healthcare with AutoGen

Starting the service

First set the name of your deployment and the namespace.

```bash
name="preventative-healthcare"
namespace="my-namespace"
```

Then build the dependencies:

```bash
helm dependency build
```

Use `helm template` to assemble the template, and pass the output to `kubectl apply` to start it up on kubernetes:

```bash
helm template $name . |  kubectl apply -f - -n $namespace
```

When the blueprint service has started, port-forward 8501 to be able to access the UI. The UI will then be available at <http://localhost:8501>

```bash
kubectl port-forward services/aimsb-preventative-healthcare-$name 8501:8501 -n $namespace
```

This blueprint will work only when the LLM service is also up and running. Note that the default model used is large and can take ~10 minutes to start.
