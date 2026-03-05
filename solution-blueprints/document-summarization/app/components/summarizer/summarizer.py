# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Document summarization logic using LangChain.
Supports multiple summarization strategies: stuff, truncate, map_reduce, refine.
"""

import os
from typing import Optional

from fastapi.responses import StreamingResponse
from langchain_classic.chains import load_summarize_chain
from langchain_classic.docstore.document import Document
from langchain_classic.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.load import dumps as langchain_dumps
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

# Prompt templates
TEMPLATE_EN = """Write a concise summary of the following text.


"{text}"


SUMMARY:"""

TEMPLATE_ZH = """请简要概括以下内容。仅输出摘要，不要添加其他内容:


"{text}"


概况:"""

TEMPLATE_REFINE_EN = """Your job is to produce a final summary.
We have provided an existing summary up to a certain point, then we will provide more context.
You need to refine the existing summary (only if needed) with new context and generate a final summary.


Existing Summary:
"{existing_answer}"



New Context:
"{text}"



Final Summary:

"""

TEMPLATE_REFINE_ZH = """\
你的任务是生成一个最终摘要。
我们已经处理好部分文本并生成初始摘要, 并提供了新的未处理文本
你需要根据新提供的文本，结合初始摘要，生成一个最终摘要。


初始摘要:
"{existing_answer}"



新的文本:
"{text}"



最终摘要:

"""

# Environment variables
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", 8192))
MAX_TOTAL_TOKENS = int(os.getenv("MAX_TOTAL_TOKENS", 16384))

LOGFLAG = os.getenv("LOGFLAG", False)


class DocumentSummarizer:
    """Handles document summarization with multiple strategies."""

    SUMMARY_TYPES = ["auto", "stuff", "truncate", "map_reduce", "refine"]

    def __init__(self, llm_endpoint: str, model_name: str, tokenizer=None):
        """
        Initialize the summarizer.

        Args:
            llm_endpoint: URL of the LLM service (e.g., AIM/vLLM endpoint)
            model_name: Name of the model to use
            tokenizer: HuggingFace tokenizer for token counting (optional, required for auto/refine/map_reduce modes)
        """
        self.llm_endpoint = llm_endpoint
        self.model_name = model_name
        self.tokenizer = tokenizer

    def _get_llm_client(
        self,
        max_tokens: int = 1024,
        temperature: float = 0.01,
        top_p: float = 0.95,
        stream: bool = False,
        timeout: Optional[float] = None,
        access_token: Optional[str] = None,
    ) -> ChatOpenAI:
        """Create a ChatOpenAI client."""
        headers = {}
        if access_token:
            headers = {"Authorization": f"Bearer {access_token}"}

        return ChatOpenAI(
            api_key="EMPTY",
            base_url=self.llm_endpoint,
            model=self.model_name,
            default_headers=headers,
            max_tokens=max_tokens,
            streaming=stream,
            temperature=temperature,
            timeout=timeout,
            model_kwargs={
                "top_p": top_p,
            },
        )

    def _get_templates(self, language: str):
        """Get prompt templates based on language."""
        if language in ["en", "auto"]:
            return TEMPLATE_EN, TEMPLATE_REFINE_EN
        elif language in ["zh"]:
            return TEMPLATE_ZH, TEMPLATE_REFINE_ZH
        else:
            raise NotImplementedError('Please specify the input language in "en", "zh", "auto"')

    def _determine_summary_type(self, message: str, summary_type: str) -> str:
        """Determine the actual summary type based on input length."""
        if summary_type != "auto":
            return summary_type

        if self.tokenizer is None:
            return "stuff"

        token_len = len(self.tokenizer.encode(message))

        if token_len < MAX_INPUT_TOKENS:
            return "stuff"

        return "map_reduce"

    def _create_text_splitter(self, summary_type: str, max_tokens: int):
        """Create appropriate text splitter based on summary type."""
        if summary_type == "stuff":
            # For stuff mode, use larger chunk size to avoid splitting small documents
            return CharacterTextSplitter(chunk_size=10000, chunk_overlap=0, separator="\n\n")

        chunk_size_cfg = -1
        chunk_overlap_cfg = -1

        if summary_type == "refine":
            if MAX_TOTAL_TOKENS <= 2 * max_tokens + 256 or MAX_INPUT_TOKENS <= max_tokens + 256:
                raise RuntimeError(
                    "In Refine mode, please set MAX_TOTAL_TOKENS larger than (max_tokens * 2 + 256), "
                    "MAX_INPUT_TOKENS larger than (max_tokens + 256)"
                )
            max_input_tokens = min(MAX_TOTAL_TOKENS - 2 * max_tokens - 256, MAX_INPUT_TOKENS - max_tokens - 256)
        else:
            if MAX_TOTAL_TOKENS <= max_tokens + 256 or MAX_INPUT_TOKENS < 256:
                raise RuntimeError(
                    "Please set MAX_TOTAL_TOKENS larger than max_tokens + 256, MAX_INPUT_TOKENS larger than 256"
                )
            max_input_tokens = min(MAX_TOTAL_TOKENS - max_tokens - 256, MAX_INPUT_TOKENS - 256)

        chunk_size = min(chunk_size_cfg, max_input_tokens) if chunk_size_cfg > 0 else max_input_tokens
        chunk_overlap = chunk_overlap_cfg if chunk_overlap_cfg > 0 else int(0.1 * chunk_size)

        if self.tokenizer is None:
            # Fallback to character-based splitting
            return CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=self.tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    async def summarize(
        self,
        text: str,
        summary_type: str = "auto",
        language: str = "auto",
        top_p: float = 0.95,
        max_tokens: int = 1024,
        temperature: float = 0.01,
        timeout: Optional[float] = None,
        access_token: Optional[str] = None,
        stream: bool = False,
    ):
        """
        Summarize the given text.

        Args:
            text: The text to summarize
            summary_type: One of 'auto', 'stuff', 'truncate', 'map_reduce', 'refine'
            language: Language of the text ('en', 'zh', 'auto')
            max_tokens: Maximum tokens for the output
            top_p: Top-p sampling parameter
            temperature: Temperature for generation
            stream: Whether to stream the response
            timeout: Request timeout
            access_token: Optional bearer token for authentication

        Returns:
            Generated summary text or StreamingResponse
        """
        if summary_type not in self.SUMMARY_TYPES:
            raise NotImplementedError(f"Please specify the summary_type in {self.SUMMARY_TYPES}")

        # Determine actual summary type
        actual_summary_type = self._determine_summary_type(text, summary_type)

        # Map reduce doesn't support streaming
        if stream and actual_summary_type == "map_reduce":
            if LOGFLAG:
                print("Map Reduce mode doesn't support stream=True, setting to stream=False")
            stream = False

        # Get templates
        templ, templ_refine = self._get_templates(language)
        prompt = PromptTemplate.from_template(templ)
        prompt_refine = PromptTemplate.from_template(templ_refine) if actual_summary_type == "refine" else None

        # Split text
        text_splitter = self._create_text_splitter(actual_summary_type, max_tokens)
        texts = text_splitter.split_text(text)
        docs = [Document(page_content=t) for t in texts]

        if LOGFLAG:
            print(f"Split input into {len(docs)} chunks")

        # Create LLM client
        client = self._get_llm_client(
            max_tokens=max_tokens,
            top_p=top_p,
            temperature=temperature,
            stream=stream,
            timeout=timeout,
            access_token=access_token,
        )

        # Create summarization chain
        if actual_summary_type == "stuff":
            llm_chain = load_summarize_chain(llm=client, prompt=prompt)
        elif actual_summary_type == "truncate":
            docs = [docs[0]]
            llm_chain = load_summarize_chain(llm=client, prompt=prompt)
        elif actual_summary_type == "map_reduce":
            llm_chain = load_summarize_chain(
                llm=client,
                map_prompt=prompt,
                combine_prompt=prompt,
                chain_type="map_reduce",
                return_intermediate_steps=False,
            )
        elif actual_summary_type == "refine":
            llm_chain = load_summarize_chain(
                llm=client,
                question_prompt=prompt,
                refine_prompt=prompt_refine,
                chain_type="refine",
                return_intermediate_steps=False,
            )
        else:
            raise NotImplementedError(f"Unknown summary type: {actual_summary_type}")

        # Execute
        if stream:

            async def stream_generator():
                async for chunk in llm_chain.astream_log(docs):
                    data = langchain_dumps({"ops": chunk.ops})
                    if LOGFLAG:
                        print(data)
                    yield f"data: {data}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            response = await llm_chain.ainvoke(docs)
            output_text = response["output_text"]
            if LOGFLAG:
                print(f"Summary output: {output_text}")
            return output_text
