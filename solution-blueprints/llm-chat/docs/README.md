<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# LLM-Chat

The initial evaluation of an LLM is often best done by chatting with it. This is a sanity check, and lets us quickly get a feel for what the LLM is capable of and what style of responses it tends to generate. The LLM-Chat AIM Solution Blueprint makes that easy. Even before standardised test suites, we can explore prompting techniques and understand model behavior. Some qualities of LLMs are difficult to capture in a quantitative evaluation. It's important to interact with the LLM before embedding it into any critical enterprise workflows.

This simple solution blueprint consists of just two parts: the open source [OpenWebUI](https://openwebui.com/)  chat application, and the user's chosen LLM deployed alongside it.

## Architecture diagram

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="LLM-Chat consists of just two components: the OpenWebUI server and the AIM LLM." src="architecture-diagram-light-scheme.png">
</picture>

## What's included?

AIM Solution Blueprints are Kubernetes applications packaged with [Helm](https://helm.sh/). It takes one click to launch them in an AMD Enterprise AI cluster and test them out.

### Key features
- A feature-rich, user-friendly LLM Chat platform provided by the open source [OpenWebUI](https://openwebui.com/)
    - OpenWebUI is extensible and configurable. This blueprint showcases a minimalist configuration without clutter from unneeded features.
- Freely choose any AIM LLM
    - AIM LLMs provide a robust, scalable inference runtime that is optimized for AMD hardware.
- Talk with the AIM in a back-and-forth classic chat interface and get access to a wide array of inference parameters like the system prompt, temperature, various constraints, etc.


### Software Used in This Blueprint
- AIM (Any LLM)
- OpenWebUI

### Minimum System Requirements
Kubernetes cluster with AMD GPU nodes (exact number of GPUs depends on AIM LLM)


## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
