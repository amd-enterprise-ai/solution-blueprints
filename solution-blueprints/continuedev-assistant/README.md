<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Continue.dev Coding Assistant

This helm chart deploys the [code-server](https://github.com/coder/code-server) browser IDE application, its extension [Continue.dev]( https://www.continue.dev/) and Qwen Coder LLMs.

## Deploying

First set the name of your deployment and the namespace.
```bash
name=testing-coding-assistant
namespace=my-namespace
```
Then run
```bash
helm dependency build .
helm template $name . \
    | kubectl apply -f - -n$namespace
```

Then, to connect to the code-server, port-forward 8080 to be able to access the UI. The UI will then be available at <http://localhost:8080>.

```bash
kubectl port-forward services/aimsb-continuedev-assistant-$name 8080:80 -n $namespace
```

## Browser recommendation

Note that the continue.dev assistant and code-server functionality may not work perfectly in every browser. This has been tested to work with Chrome.
