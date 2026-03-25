# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Centralised prompt templates and canned messages for the Agentic RAG system.

Every string the LLM sees (system prompts, grading rubrics, search instructions,
fallback messages) lives here.  Keeping them in one file makes it easy to tune
agent behaviour, A/B-test prompt variants, or swap prompt sets per agent — all
without touching the orchestration logic in rag_agent.py.
"""

# ---------------------------------------------------------------------------
# 1. ANSWER GENERATION
# ---------------------------------------------------------------------------

# Anti-hallucination prompt: forces the LLM to answer ONLY from retrieved context.
# Key rules: no outside knowledge, include all matching items, no source citations.
ANSWER_SYSTEM_PROMPT = (
    "You are a strict document analyst. Your ONLY source of knowledge is the "
    "'Retrieved Context' section below. You have NO prior knowledge whatsoever.\n\n"
    "RULES:\n"
    "1. Answer using ONLY facts that are EXPLICITLY AND DIRECTLY STATED in the Retrieved Context.\n"
    "2. Be thorough — include ALL relevant information from the context: direct answers, "
    "   surrounding background, supporting details, and related facts that help fully "
    "   understand the answer. Do not omit context that enriches the response even if "
    "   it was not explicitly asked for.\n"
    "3. If the context mentions MULTIPLE items that match the question, include ALL of them. "
    "   EXCEPTION: for questions using superlatives or asking for judgment "
    "   ('most', 'best', 'main', 'primary', 'most interesting', 'least', 'worst'), "
    "   identify and state the SINGLE BEST answer with a brief justification from the text.\n"
    "4. NEVER infer, interpret, or imply. Only report what is written verbatim or paraphrased directly. "
    "   Words like 'implies', 'suggests', 'probably', or 'this means' are FORBIDDEN.\n"
    "5. NEVER fill in gaps with outside knowledge, even if you know the answer.\n"
    "6. If the context does not explicitly state the specific answer, "
    "   report what the context DOES explicitly say that is related, then note what is missing.\n"
    "7. Do NOT say the documents lack information — the context has already been verified "
    "   as relevant. Always extract and report whatever relevant content is present.\n"
    "8. Do NOT add source citations or references."
)

# Hard-coded fallback when zero relevant contexts survive grading.
# Returned directly (no LLM call) to prevent hallucination from parametric knowledge.
NOT_FOUND_MESSAGE = (
    "I was unable to find relevant information in the uploaded documents to answer "
    "your question. The documents may not contain information about this topic. "
    "Please try uploading documents that cover this subject, or rephrase your question."
)

# ---------------------------------------------------------------------------
# 2. COMPLETENESS CHECK
# ---------------------------------------------------------------------------

# Used after the first YES verdict to decide if we need another search.
# FULLY → stop and answer.  PARTIALLY → search again for missing parts.
# Only runs when search_count < 2 to avoid wasting attempts.
COMPLETENESS_PROMPT_TEMPLATE = (
    "Question: {question}\n\n"
    "Context found so far:\n{context}\n\n"
    "Does this context contain enough information to answer the question?\n"
    "- If the context clearly addresses the topic and provides a meaningful answer, reply FULLY.\n"
    "- Only reply PARTIALLY if a specific named fact (a person, date, number, or event) "
    "  is explicitly asked for and is clearly absent from the context.\n"
    "- When in doubt, reply FULLY. Do not search for more if the core question is answered.\n"
    "Reply with EXACTLY one word: FULLY or PARTIALLY."
)

# ---------------------------------------------------------------------------
# 3. RELEVANCE GRADING
# ---------------------------------------------------------------------------

# Intentionally lenient to avoid rejecting topically-related content.
# Grading happens after each retrieval; YES promotes content to relevant_contexts.
GRADER_PROMPT_TEMPLATE = (
    "Question: {question}\n\n"
    "Retrieved Text:\n{text}\n\n"
    "Does this text mention ANY of the topics, people, events, or concepts in the question?\n"
    "Answer YES if the text is about the same subject, characters, or setting — "
    "even if it only partially addresses the question or provides background context.\n"
    "Answer NO only if the text is completely unrelated to the question topic.\n"
    "When in doubt, answer YES.\n"
    "Answer YES or NO."
)

# Used when the retrieval returns multiple chunks (separator: \n\n---\n\n).
# Asks the LLM to identify which individual chunks are relevant in one pass.
MULTI_CHUNK_GRADER_PROMPT = (
    "Question: {question}\n\n"
    "Below are {n} retrieved text passages, numbered [1] to [{n}].\n"
    "Mark a passage as relevant if it mentions ANY of the same topics, characters, "
    "events, or concepts as the question — even if it only partially addresses it "
    "or provides background context. Err on the side of including passages.\n"
    "Mark a passage as NOT relevant ONLY if it is completely unrelated to the question topic.\n\n"
    "{passages}\n\n"
    "List ONLY the numbers of the relevant passages, separated by commas. "
    "If truly none are related to the topic at all, output: NONE\n"
    'Examples: "1, 3" or "2" or "NONE"'
)

# Injected into conversation when the grader rejects a retrieval,
# so the reasoner knows to try a different search strategy.
GRADER_REJECT_HINT = "Previous search was not relevant. Try different keywords."

# ---------------------------------------------------------------------------
# 4. SEARCH / TOOL-USE INSTRUCTIONS
# ---------------------------------------------------------------------------

# Base instruction given to the LLM when it should search instead of answer.
SEARCH_SYSTEM_PROMPT = (
    "You are a RAG Analyst. You MUST use the 'retrieve_documents' tool to search for information. "
    "Do NOT answer from memory. Use the tool now."
)

# Appended when we already have PARTIAL info and need more.
# Placeholders: {past_queries} — comma-separated quoted list, {found_preview} — snippet.
SEARCH_PARTIAL_ADDENDUM = (
    "\n\nYou already searched with: {past_queries} and found PARTIAL information. "
    'Here is a summary of what was already found: "{found_preview}..." '
    "Some parts of the question are still unanswered. "
    "You MUST use a DIFFERENT search query. "
    "Search for the MISSING aspects using different keywords, synonyms, "
    "or related terms. Do NOT repeat previous queries."
)

# Appended when all previous searches returned zero relevant results.
# Placeholder: {past_queries} — comma-separated quoted list.
SEARCH_FAILED_ADDENDUM = (
    "\n\nIMPORTANT: The following searches FAILED to find relevant info: {past_queries}. "
    "You MUST use COMPLETELY DIFFERENT keywords and phrasing. "
    "Try shorter queries, synonyms, or alternative terms related to the topic."
)

# Injected when the retrieved content is identical to a previous retrieval.
# Forces the reasoner to pivot to fundamentally different keywords.
GRADER_DUPLICATE_HINT = (
    "DUPLICATE: The last search returned IDENTICAL content to a previous search. "
    "You MUST try a completely different approach — use only the character name, "
    "or a single key noun from the question, or a synonym. "
    "Do NOT rephrase the same query."
)

# Last-ditch nudge when the LLM ignores tool_calls on the first attempt.
SEARCH_FORCE_NUDGE = "Use the retrieve_documents tool NOW to search."
