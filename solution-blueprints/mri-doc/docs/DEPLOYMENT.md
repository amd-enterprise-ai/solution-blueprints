<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Helm deployment
Solution Blueprints are provided as Helm Charts.

The recommended approach to deploy them is to pipe the output of `helm template` to `kubectl apply -f -`.
We do not recommend `helm install`, which by default uses a Secret to keep track of the related resources.
This does not work well with Enterprise clusters that often have limitations on the kinds of resources that
regular users are allowed to create.

## Start Helm template

## Option 1: Demo Deployment with Self-Hosted LLMs

This option deploys two pods, one will host the default LLM gpt-oss-20b, and the second the user interface:
```bash
name="mri-doc"
namespace="default"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-mri-doc \
  | kubectl apply -f - -n $namespace
```

## Option 2: Using an existing deployment or external LLM
By default, any required AIMs are deployed by the helm chart. If you already have a compatible AIM deployed, you can use that instead, and reuse resources.

To use an existing deployment or external LLM, set the value `llm.existingService` to that endpoint. Then, any other values you pass in the `llm` mapping are ignored, and your existing service is used instead. You should use the Kubernetes Service name, or if the service is in a different namespace, you can use the long form `<SERVICENAME>.<NAMESPACE>.svc.cluster.local:<SERVICEPORT>`. If needed, you can pass a whole URL.

Full example command:
```bash
name="mri-doc"
namespace="default"
servicename="aim-llm-my-model-123456"

helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-mri-doc \
  --set llm.existingService=$servicename \
  | kubectl apply -f - -n $namespace
```

## Connecting

### Option 1: Port Forwarding

Then, to connect to the UI, port-forward any chosen port, e.g., 7861, to be able to access the UI. The UI will then be available at http://localhost:7861.

```bash
kubectl port-forward services/aimsb-mri-doc-$name 7861:80 -n $namespace
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
name="mri-doc"
namespace="default"
servicename="aim-llm-my-model-123456"
helm template $name oci://registry-1.docker.io/amdenterpriseai/aimsb-mri-doc \
  --set llm.existingService=$servicename \
  --set http_route.enabled=true \
  | kubectl apply -f - -n $namespace
```

**Obtaining the URL:**

The URL to access the blueprint via HTTPRoute is formed by the service name and the hostname of the gateway. Use this command to produce the URL by querying the hostname from the cluster:
   ```bash
   echo "https://aimsb-mri-doc-$name$(kubectl get gtw -A -o jsonpath='{.items[*].spec.listeners[?(@.name=="https")].hostname}' | tr -d \*)/"
   ```
