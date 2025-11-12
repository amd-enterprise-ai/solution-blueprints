<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Financial Stock Intelligence (FSI)

Starting the service

First set the name of your deployment, and the namespace where to deploy it.

```bash
name="fsi-example"
namespace="default"
```

Then build the dependencies:

```bash
helm dependency build
```

Use `helm template` to assemble the template, and pass the output to `kubectl apply` to start it up on kubernetes:

```bash
helm template $name . |  kubectl apply -f - -n $namespace
```

When the service has started, set up port forwarding to be able to access the UI. The UI will then be available at <http://localhost:8080>

```bash
kubectl port-forward services/aimsb-fsi-$name 8080:80 -n $namespace
```

The FSI solution will work only when the LLM service is also up and running. Note that the default model used is large and can take ~10 minutes to start.
