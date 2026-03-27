<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AutoGen Multi-Agent Preventative Healthcare Team

This is a multi-agent system built on top of [AutoGen](https://github.com/microsoft/autogen) agents designed to automate and optimize preventative healthcare outreach. It uses multiple agents, large language models (LLMs) and asynchronous programming to streamline the process of identifying patients who meet specific screening criteria and generating personalized outreach emails.

The system uses an AIMS model endpoint with the inference.

Credit: Though heavily modified, the original idea comes from Mike Lynch on his [Medium blog](https://medium.com/@micklynch_6905/hospitalgpt-managing-a-patient-population-with-autogen-powered-by-gpt-4-mixtral-8x7b-ef9f54f275f1).

## Workflow:

<picture>
  <source media="(prefers-color-scheme: light)" srcset="prev-healthcare-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="prev-healthcare-dark-scheme.png">
  <img alt="The Preventative Healthcare application runs inside a single container. It is served by an AIM LLM deployed beside it." src="prev-healthcare-light-scheme.png">
</picture>

1. **Define screening criteria**: After getting the general screening task from the user, the User Proxy Agent starts a conversation between the Epidemiologist Agent and the Doctor Critic Agent to define the criteria for patient outreach based on the target screening type. The output criteria is age range (e.g., 40–70), gender, and relevant medical history.

2. **Select and identify patients based on the screening criteria**: The Assistant Agent filters patient data from a CSV file based on the defined criteria, including age range, gender, and medical conditions. The patient data were synthetically generated. You can find the sample data under `data/patients.csv`.

3. **Generate outreach emails**: The program generates outreach emails for the filtered patients using LLMs and saves them as text files.

## Usage

1. Upload an tabular dataset on patient records.
2. Provide the context of the screening task e.g. diabetes screening.
3. Run the analysis.
4. Click on "Generate Outreach Emails" to create draft emails to patients (.txt files with email drafts) and download them.

## Disclaimer

This tool is for research and educational use only. It is not intended for clinical diagnosis or treatment.

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third party software and materials used within the Solution Blueprints are governed by their respective licenses.
