<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# MRI Analysis Tool

Starting the service

First set the name of your deployment, and the namespace where to deploy it.

```bash
name="mri-doc"
namespace="default"
```

Then build the dependencies:

```bash
helm dependency build
```

Use `helm template` to assemble the template, and pass the output to `kubectl apply` to start it up on Kubernetes:

```bash
helm template $name . | kubectl apply -f - -n $namespace
```

When the service has started, set up port forwarding to be able to access the UI. The UI will then be available at http://localhost:7861

```bash
kubectl port-forward services/aimsb-mri-doc-$name 7861:80 -n $namespace
```
