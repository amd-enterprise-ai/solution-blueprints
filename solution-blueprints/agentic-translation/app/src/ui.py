# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
import os
import urllib.parse
from time import sleep

import requests
import streamlit as st
from prompts import (
    CRITIQUE_SYSTEM_MESSAGE,
    JUDGE_SYSTEM_MESSAGE,
    JUDGEMENT_PROMPT,
    PROMPT_HISTORY,
    REFLECTION_PROMPT,
    TRANSLATION_INSTRUCTION,
    TRANSLATION_PROMPT,
    TRANSLATOR_SYSTEM_MESSAGE,
)

translate_base_url = os.environ["TRANSLATE_BASE_URL"]

chat_message_avatars = {"action": "🗣️", "critique": "🔍", "judge": "🏛️", "final translation": "📄", "error": "❌"}

st.title("Agentic translation")

with st.spinner("Waiting for translation engine..."):
    # readiness check for translation api
    while True:
        try:
            r = requests.get(urllib.parse.urljoin(translate_base_url, "/readiness"), timeout=2)
            if r.status_code == 200:
                break
            sleep(1)
        except requests.exceptions.RequestException:
            sleep(1)

col1, col2 = st.columns(2)
source_language = col1.text_input("Source Language")
target_language = col2.text_input("Target Language")
source_text = st.text_area("Source Text", height=300)
instruction = st.text_area("Instruction", height=100)

context = {
    "source_language": source_language,
    "target_language": target_language,
    "source_text": source_text,
    "instruction": instruction,
}

with st.expander("Modify prompts:"):
    context["translator_system_message"] = st.text_area(
        "translator_system_message", TRANSLATOR_SYSTEM_MESSAGE, height=100
    )
    context["translation_prompt"] = st.text_area("translation_prompt", TRANSLATION_PROMPT, height=100)
    context["translation_instruction"] = st.text_area("translation_instruction", TRANSLATION_INSTRUCTION, height=100)
    context["prompt_history"] = st.text_area("prompt_history", PROMPT_HISTORY, height=100)

    context["critique_system_message"] = st.text_area("critique_system_message", CRITIQUE_SYSTEM_MESSAGE, height=100)
    context["reflection_prompt"] = st.text_area("reflection_prompt", REFLECTION_PROMPT, height=100)

    context["judge_system_message"] = st.text_area("judge_system_message", JUDGE_SYSTEM_MESSAGE, height=100)
    context["judgement_prompt"] = st.text_area("judgement_prompt", JUDGEMENT_PROMPT, height=100)

    max_iterations = st.number_input("Max iterations", min_value=1, value=3)
    max_tokens = st.number_input("Max tokens per chunk", min_value=500, value=2000)

if "responses" not in st.session_state:
    st.session_state.responses = []

if st.button("Translate"):
    if context["target_language"] == "":
        st.error("Please fill in target language.")
        st.stop()
    if context["source_text"] == "":
        st.error("Please fill in text to translate.")
        st.stop()
    st.session_state.responses = []
    with st.spinner("Translating..."):
        payload = {
            "context": context,
            "max_iterations": max_iterations,
            "max_tokens": max_tokens,
        }
        response = requests.post(urllib.parse.urljoin(translate_base_url, "/translate"), json=payload, stream=True)
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            try:
                data = json.loads(chunk)
            except json.decoder.JSONDecodeError:
                # If the API returns something unexpected, consider it an error and show the raw response
                data = {"agent": "error", "content": chunk}
            st.session_state.responses.append(data)
            with st.chat_message(data["agent"], avatar=chat_message_avatars.get(data["agent"])):
                st.markdown(f"**{data['agent'].capitalize()}:**")
                st.markdown(data["content"])
else:
    with st.spinner("Translating..."):
        for data in st.session_state.responses:
            with st.chat_message(data["agent"], avatar=chat_message_avatars.get(data["agent"])):
                st.markdown(f"**{data['agent'].capitalize()}:**")
                st.markdown(data["content"])
