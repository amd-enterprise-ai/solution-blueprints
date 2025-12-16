<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Talk to your documents

This blueprint deploys a Retrieval-Augmented Generation (RAG) application which allows you to talk to your documents. It uses a vector database (ChromaDB) to store document embeddings and a large language model (LLM) to answer questions based on the retrieved context.

## Deploying

The following commands should be run from the `solution-blueprints/talk-to-your-documents` directory.

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
kubectl port-forward services/$name-aimsb-talk-to-your-documents 7860:80
```

The application will be fully functional once the LLM, embedding and vectordb services are up and running. Note that the default models can be large and may take some time to start.
