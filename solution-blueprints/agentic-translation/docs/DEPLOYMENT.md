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
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-translation \
  | kubectl apply -f - -n $namespace
```

## Using an existing deployment or external LLM
By default, any required AIMs are deployed by the helm chart. If you already have a compatible AIM deployed, you can use that instead, and reuse resources.

To use an existing deployment or external LLM, set the value `llm.existingService` to that endpoint. Then, any other values you pass in the `llm` mapping are simply ignored, and your existing service is used instead. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

Full example command:
```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-translation \
  --set llm.existingService=$servicename \
  | kubectl apply -f - -n $namespace
```

## Default AIM image and GPU compatibility

By default, the chart deploys Meta Llama 3.3 70B with this AIM: `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.8.5-preview`

On newer GPUs, this default image may not be the best match and can fail to start or run sub-optimally.
To choose a newer AIM or deploy a different LLM, override `llm.image` to a compatible image. See the [catalog of available AIMs](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html) for options.

Example:

```bash
name="my-deployment"
namespace="my-namespace"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-translation \
  --set llm.image=amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:<NEWER_TAG> \
  | kubectl apply -f - -n $namespace
```

## Using a custom image and imagePullSecrets

To use a custom version of the image from another repo, you can set the `image` and `imagePullSecrets`, if necessary, from the command line as follows:

```bash
imagerepository="my-repo/custom-agentic-translation-application"
imagetag="0.0.1"
secretname="my-registry-secret"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-translation \
  --set image.repository=$imagerepository \
  --set image.tag=$imagetag \
  --set imagePullSecrets[0].name=$secretname \
  | kubectl apply -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding

Then, to connect to the UI, port-forward 8501 to be able to access the UI. The UI will then be available at <http://localhost:8501>

```bash
kubectl port-forward service/aimsb-agentic-translation-$name 8501:8501 -n $namespace
```

### Option 2: HTTPRoute (Gateway Access)

If your cluster has a Gateway API compatible gateway (e.g., Kubernetes Gateway, Istio, etc.), you can enable HTTPRoute creation to route traffic through the gateway.

**Prerequisites:**
- A Gateway named `https` must exist in the `kgateway-system` namespace (or configure a different gateway)
- The Gateway must be properly configured with listeners

**Enabling HTTPRoute:**

Use `--set http_route.enabled=true` in the `helm template` command to enable HTTPRoute creation:
(notice, the command contains an existing Llm service running in the cluster).

```bash
name="my-deployment"
namespace="my-namespace"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-agentic-translation \
  --set llm.existingService=$servicename \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
   ```bash
   echo "https://aimsb-agentic-translation-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
   ```
