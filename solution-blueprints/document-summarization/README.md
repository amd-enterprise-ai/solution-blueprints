<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Document Summarization

Starting the service

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
helm template $name . \
  | kubectl apply -f - -n $namespace
```

When the DocSum service has started, port-forward 5173 to be able to access the UI. The UI will then be available at <http://localhost:5173>

```bash
kubectl port-forward services/aimsb-docsum-$name-ui 5173:5173 -n $namespace
```

Summarization will work only when the LLM service is also up and running. Note that the default model used can take several minutes to start.
