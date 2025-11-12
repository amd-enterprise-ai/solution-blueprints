<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AutogenStudio Helm Chart

AutogenStudio is a web-based interface for creating, configuring, and managing multi-agent AI conversations. This Helm chart deploys AutogenStudio in a Kubernetes cluster.

## Prerequisites

- Kubernetes cluster with kubectl access
- Helm 3.x installed
- Sufficient cluster resources (2 CPU, 4Gi memory minimum)

## Quick Start

### 1. Deploy AutogenStudio

From the `solution-blueprints/autogen-studio` directory:

```bash
# First, build dependencies
helm dependency build
# Deploy helm chart
helm template --name-template "test" . \
  | kubectl apply -f -
```

This will create:
- ConfigMap with default gallery configuration
- Deployment running AutogenStudio on port 8081
- Service to expose the application
- AIM deployment and service if an existing service isn't used

### 2. Access the UI

Forward local port 8080 to AutogenStudio service:
```bash
kubectl port-forward service/autogenstudio-test 8080:8081
```

Then open your browser to: **http://localhost:8080**


### Delete the Deployment

```bash
helm --name-template "test" . \
  | kubectl delete -f -
```

Or delete individual resources:

```bash
kubectl delete deployment autogenstudio-test
kubectl delete service autogenstudio-test
kubectl delete configmap autogenstudio-test
```

Delete AIM service and deployment in the same way if needed.

## Troubleshooting

### Pod Not Starting

Check pod events and logs:

```bash
kubectl describe pod -l app=autogenstudio-test
kubectl logs -l app=autogenstudio-test
```

Common issues:
- Insufficient cluster resources
- Image pull failures
- Configuration errors

### Service Not Accessible

Verify service and endpoints:

```bash
kubectl get endpoints autogenstudio-test
kubectl get service autogenstudio-test
```

### Port Forward Issues

If port forwarding fails or you can't access the UI:

1. **Check if the port is already in use:**
   ```bash
   lsof -i :8080
   ```

2. **Try a different local port:**
   ```bash
   kubectl port-forward service/autogenstudio-test 8082:8081
   # or
   kubectl port-forward service/autogenstudio-test 9090:8081
   ```

3. **Verify the service is running:**
   ```bash
   kubectl get pods -l app=autogenstudio-test
   kubectl get service autogenstudio-test
   ```

4. **Test internal connectivity:**
   ```bash
   # Test if AutogenStudio responds inside the pod
   kubectl exec deployment/autogenstudio-test -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8081
   # Should return: 200
   ```

5. **Check AutogenStudio logs:**
   ```bash
   kubectl logs deployment/autogenstudio-test --tail=20
   # Look for: "Application startup complete. Navigate to http://127.0.0.1:8081"
   ```

6. **Kill existing port forwards and retry:**
   ```bash
   # Kill any existing kubectl port-forward processes
   pkill -f "kubectl port-forward"

   # Start fresh port forwarding
   kubectl port-forward service/autogenstudio-test 8080:8081
   ```

## AutogenStudio Features

Once connected to the UI, you can:

- **Create Agents**: Define AI agents with specific roles and capabilities
- **Configure Models**: Set up different LLM models and parameters
- **Design Workflows**: Create multi-agent conversation flows
- **Test Interactions**: Run and debug agent conversations
- **Manage Galleries**: Import/export agent configurations
- **Monitor Performance**: View conversation logs and metrics
