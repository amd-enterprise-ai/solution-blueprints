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

To use an existing deployment or external LLM for the Agent/Edit/Chat functionality, set the value `chatLLM.existingService` to that endpoint. Then, any other values you pass in the `chatLLM` mapping are simply ignored, and your existing service is used instead. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

Similarly, you may use an existing deployment for the Autocomplete functionality. Set the value `autocompleteLLM.existingService` to that endpoint.

Full example command:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
autocompleteservicename="aim-llm-my-autocomplete-123"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-continuedev-assistant \
  --set chatLLM.existingService=$servicename \
  --set autocompleteLLM.existingService=$autocompleteservicename \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and GPU compatibility

By default, the chart deploys these AIMs:

- `chatLLM.image=amdenterpriseai/aim-qwen-qwen3-32b:0.8.5`
- `autocompleteLLM.image=amdenterpriseai/aim-base:0.9`

On newer GPUs, these images may not be the best match and can fail to start or run sub-optimally.
To choose newer AIMs or deploy different LLMs, override `chatLLM.image` and/or `autocompleteLLM.image` to compatible images. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-continuedev-assistant \
  --set chatLLM.image=amdenterpriseai/aim-qwen-qwen3-32b:<NEWER_TAG> \
  --set autocompleteLLM.image=amdenterpriseai/aim-base:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding
Then, to connect to the UI, port-forward any chosen port, e.g., 8083, to be able to access the UI. The UI will then be available at <http://localhost:8083>.

```bash
kubectl port-forward services/aimsb-continuedev-assistant-$name 8083:80 -n $namespace
```

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway).
- The Gateway must be properly configured with listeners.

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:
(notice, the command contains an existing Llm service running in the cluster).

```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
autocompleteservicename="aim-llm-my-autocomplete-123"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-continuedev-assistant \
  --set chatLLM.existingService=$servicename \
  --set autocompleteLLM.existingService=$autocompleteservicename \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
   ```bash
   echo "https://aimsb-continuedev-assistant-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
   ```

## Using continue.dev
The continue.dev extension is installed and by default appears inside the extensions tab on the left hand side. The user experience is probably best if you drag the extension to the right side pane (see point three [here](https://docs.continue.dev/ide-extensions/install)).
To get familiar with continue.dev features, see [the quick start guide](https://docs.continue.dev/ide-extensions/quick-start).

## Browser recommendation

Note that the continue.dev assistant and code-server functionality may not work perfectly in every browser. This has been tested with Chrome.
