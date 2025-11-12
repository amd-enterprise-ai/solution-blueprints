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
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-continuedev-assistant \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external LLM
By default, any required AIMs are deployed by the helm chart. If you already have a compatible AIM deployed, you can use that instead, and reuse resources.

To use an existing deployment or external LLM for the Agent/Edit/Chat functionality, set the value `chat.llm.existingService` to that endpoint. Then, any other values you pass in the `chat.llm` mapping are simply ignored, and your existing service is used instead. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

Similarly, you may use an existing deployment for the Autocomplete functionality. Set the value `autocomplete.llm.existingService` to that endpoint.

Full example command:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
autocompleteservicename="aim-llm-my-autocomplete-123"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-continuedev-assistant \
  --set chat.llm.existingService=$servicename \
  --set autocomplete.llm.existingService=$autocompleteservicename \
  | kubectl apply -f - -n $namespace
```

## Connecting

Then, to connect to the code-server, port-forward 8080 to be able to access the UI. The UI will then be available at <http://localhost:8080>.

```bash
kubectl port-forward services/aimsb-continuedev-assistant-$name 8080:80 -n $namespace
```

## Browser recommendation

Note that the continue.dev assistant and code-server functionality may not work perfectly in every browser. This has been tested with Chrome.
