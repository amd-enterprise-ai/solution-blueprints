<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Helm deployment
Solution Blueprints are provided as Helm Charts.

The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We don't recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

An example for command-line usage:
```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external services
By default, any required AIMs (LLM, Embedding, ChromaDB) are deployed by the helm chart. If you already have compatible services deployed, you can use them instead, and reuse resources.

To use an existing deployment, set the `existingService` value for the respective component. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

### External LLM
Set `llm.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set llm.existingService="http://my-llm-service:8000" \
  | kubectl apply -f - -n $namespace
```

### External Embedding Service
Set `embedding.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set embedding.existingService="http://my-embedding-service:7997" \
  | kubectl apply -f - -n $namespace
```

### External ChromaDB
Set `chromadb.existingService` to the endpoint.
```bash
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-talk-to-your-documents \
  --set chromadb.existingService="http://my-chromadb-service:8000" \
  | kubectl apply -f - -n $namespace
```

You can combine these flags as needed.

## Connecting

Then, to connect to the UI, port-forward 7860 to be able to access the UI. The UI will then be available at <http://localhost:7860>.

```bash
kubectl port-forward services/$name-aimsb-talk-to-your-documents 7860:80 -n $namespace
```
