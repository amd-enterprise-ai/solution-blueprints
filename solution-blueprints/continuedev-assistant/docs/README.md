<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# continue.dev Coding Assistant

The continue.dev Coding Assistant is an AI pair programmer that integrates into your code editor (IDE). In this Solution Blueprint, the assistant is installed in code-server, which provides a browser-based IDE. Continue.dev uses Large Language Models (LLMs) to suggest code snippets, functions, and even entire modules as you type. This solution provides you with local LLMs of your choice to predict, fix and discuss the code while you are developing.

The coding assistant is embedded in a fully-featured IDE [code-server]( https://github.com/coder/code-server), which offers Visual Studio Code in the browser.

The Coding Assistant has multiple interaction modes:
- Chat – conversational back-and-forth with the model.
- Autocomplete – inline code completions and suggestions as you type.
- Edit – making direct modifications to selected code (e.g. “refactor this function” or “convert to async”).
- Agentic mode – higher-level planning and automation where the assistant can chain actions together (e.g. scaffold a project, set up dependencies, generate tests).

The Chat and Agent functionality are found in the continue.dev tab. Edit is available as a contextual option for selected text. Autocomplete is active in the file editor. See further instructions about the modes in the [continue.dev documentation](https://docs.continue.dev/#core-features).

The continue.dev extension is installed and by default appears inside the extensions tab on the left hand side. The user experience is probably best if you drag the extension to the right side pane (see point three [here](https://docs.continue.dev/ide-extensions/install)).
To get familiar with continue.dev features, see [the quick start guide](https://docs.continue.dev/ide-extensions/quick-start)

This solution blueprint consists of just three parts: the open source [code-server]( https://github.com/coder/code-server) browser IDE application, its available extension [Continue.dev]( https://www.continue.dev/) and AIM LLMs deployed alongside it. There's optionally a separate AIM LLM for autocompletion.

By default the code-server IDE is launched with the ROCm/Pytorch container and one GPU - perfect for developing machine learning applications.

## Architecture diagram

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The continue.dev coding assistant is comprised of three components: the code-server IDE, its extension continue.dev and AIM LLMs." src="architecture-diagram-light-scheme.png">
</picture>

## What's included?

AIM Solution Blueprints are Kubernetes applications packaged with [Helm](https://helm.sh/). It takes one click to launch them in an AMD Enterprise AI cluster and test them out.

### Key features
-	Full control over your data and privacy — no external API calls.
-	Ability to choose LLM models for your specific domain or coding style.
-	No subscription fees or usage limits — cost-effective over time.
-	Transparent and inspectable — you can log, debug, and audit everything.
-	Great for experimentation and research with different models or agents.
-	Suitable for enterprise or proprietary codebases where cloud-based tools are restricted.
- Ability to swap out the development image - have your own packages ready.

### Software Used in This Blueprint
- Main coding assistant AIM (gpt-oss-20B)
- An optional separate autocompletion AIM using the AIM Base container (Qwen2.5-Coder-7B)
- code-server (in the browser)
- continue.dev extension

### Minimum System Requirements
Kubernetes cluster with AMD GPU nodes (3 GPUs needed for default configuration)


## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
