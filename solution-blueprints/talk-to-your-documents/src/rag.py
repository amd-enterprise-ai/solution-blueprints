# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from typing import Iterator

import config
from backend import KnowledgeBase
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

logger = logging.getLogger(__name__)

# --- PROMPTS (The Instructions) ---
RAG_PROMPT = """Context: {documents} \nUser Question: {query}
Generate a concise answer based on the context."""


def get_llm():
    return ChatOpenAI(
        base_url=config.get_vllm_base_url(),
        api_key=SecretStr(config.VLLM_API_KEY or "not-needed"),
        model=config.get_gen_model(),
        temperature=0,
    )


def run_rag(query: str, kb: KnowledgeBase) -> Iterator[str]:
    yield "**🔍 Retrieving...**\n\n"
    documents = kb.retrieve(query)

    if not documents:
        yield "**❌ No documents found.**"
        yield "**Final Answer:** I couldn't find any information."
        return

    llm = get_llm()

    yield "**🧠 Generating Answer...**\n\n"

    prompt = ChatPromptTemplate.from_template(RAG_PROMPT)
    chain = prompt | llm

    result = chain.invoke({"documents": documents, "query": query})
    answer = str(result.content)

    yield f"**Final Answer:** {answer}"
