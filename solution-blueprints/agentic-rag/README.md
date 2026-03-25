<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic RAG

This blueprint deploys an Agentic Retrieval-Augmented Generation (RAG) application utilizing the Model Context Protocol (MCP). This architecture separates the reasoning agent from the data tools, allowing for a more modular and scalable deployment.

The system consists of:
* **MCP Server:** Handles document embeddings, vector storage (ChromaDB), and retrieval tools.
* **RAG Agent:** The user interface and reasoning engine that connects to the MCP server to fetch context and generate answers.

## Deploying

The following commands should be run from the `solution-blueprints/agentic-rag` directory.

First, set the name for your deployment. You can choose any name you like.
```bash
name=my-rag-app
```

Next, build the Helm chart dependencies:
```bash
helm dependency build
```

Now, deploy the application using `helm template` and `kubectl apply`.
```bash
helm template $name . | kubectl apply -f -
```

Once the services are running, you can access the user interface by port-forwarding the service. The UI will be available at <http://localhost:7860>.
```bash
kubectl port-forward services/aimsb-agentic-rag-$name-agent-app 7860:80
```

The application will be fully functional once the LLM, embedding and vectordb services are up and running. Note that the default models can be large and may take some time to start.
kubectl get all
