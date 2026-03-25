# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import re
from typing import Annotated, Any, AsyncGenerator, Dict, List, Optional, TypedDict, cast

import config  # type: ignore[attr-defined]
from backend import ingest_files  # type: ignore[attr-defined]
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from pydantic import SecretStr
from rag_prompts import (  # type: ignore[attr-defined]
    ANSWER_SYSTEM_PROMPT,
    COMPLETENESS_PROMPT_TEMPLATE,
    GRADER_DUPLICATE_HINT,
    GRADER_PROMPT_TEMPLATE,
    GRADER_REJECT_HINT,
    MULTI_CHUNK_GRADER_PROMPT,
    NOT_FOUND_MESSAGE,
    SEARCH_FAILED_ADDENDUM,
    SEARCH_FORCE_NUDGE,
    SEARCH_PARTIAL_ADDENDUM,
    SEARCH_SYSTEM_PROMPT,
)

from utils import (  # type: ignore[attr-defined]
    COMPLETENESS_CHECK_TIMEOUT,
    COMPLETENESS_CONTEXT_LIMIT,
    FOUND_PREVIEW_LIMIT,
    GRADER_CHUNK_LIMIT,
    GRADER_TEXT_LIMIT,
    GRADER_TIMEOUT,
    LLM_REQUEST_TIMEOUT,
    RETRIEVAL_TIMEOUT,
    SESSION_INIT_TIMEOUT,
    content_hash,
    logger,
    stream_agent_events,
    strip_tool_calls,
)

# Hard ceiling on retrieval attempts per query.
# The agent may stop earlier (1-2 attempts) if completeness check returns FULLY.
# Each cycle: reasoner -> retrieve -> grader -> reasoner = 3 graph steps.
MAX_SEARCHES = 3


# 1. DEFINE STATE
# LangGraph state is the shared memory across all graph nodes.
# Annotated fields with lambda x, y: x + y are ADDITIVE (each node appends, never overwrites).
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]  # Full conversation history
    relevance: str  # Latest grader verdict: "yes" or "no"
    search_count: Annotated[int, lambda x, y: x + y]  # Total searches so far (retrieve adds 1)
    context_pool: Annotated[List[str], lambda x, y: x + y]  # ALL retrieved text (for debugging)
    relevant_contexts: Annotated[List[str], lambda x, y: x + y]  # Only grader-approved text (used for answering)
    past_queries: Annotated[List[str], lambda x, y: x + y]  # Previous search queries (for retry diversity)
    completeness_verdict: str  # Latest completeness check: "FULLY", "PARTIALLY", or ""


# 2. THE AGENT
# Graph flow: START -> reasoner -> [tool_executor -> grader -> reasoner] (loop) -> END
# The reasoner decides to search or answer. tool_executor dispatches any MCP tool.
# The grader checks relevance. Loop continues until answer-ready or MAX_SEARCHES hit.
class RAGAgent:
    """Encapsulates the RAG agent graph nodes with injected dependencies.

    Dependencies (session, llm, tools_spec) are provided at construction time,
    making individual node methods independently testable.
    Use the async factory ``create()`` to build an instance with auto-discovered tools.
    """

    def __init__(self, session: ClientSession, llm: ChatOpenAI, tools_spec: List[Dict[str, Any]]) -> None:
        self.session = session
        self.llm = llm
        self.tools_spec = tools_spec

    @staticmethod
    async def discover_tools(session: ClientSession) -> List[Dict[str, Any]]:
        """Fetch available tools from MCP and convert to OpenAI function-call format.

        This replaces hardcoded TOOLS_SPEC — adding a new tool to the MCP server
        automatically makes it available to the agent.
        """
        result = await session.list_tools()
        specs: List[Dict[str, Any]] = []
        for tool in result.tools:
            spec: Dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or "",
            }
            if tool.inputSchema:
                spec["parameters"] = tool.inputSchema
            specs.append(spec)
        return specs

    @classmethod
    async def create(cls, session: ClientSession, llm: ChatOpenAI) -> "RAGAgent":
        """Async factory: discovers MCP tools and returns a ready-to-use agent."""
        tools_spec = await cls.discover_tools(session)
        logger.info(f"Discovered {len(tools_spec)} MCP tools: {[t['name'] for t in tools_spec]}")
        return cls(session=session, llm=llm, tools_spec=tools_spec)

    async def _check_completeness(self, user_question: str, relevant_contexts: List[str]) -> Optional[str]:
        """Ask the LLM whether the retrieved context fully answers the question.

        Returns:
            "FULLY" if the context is sufficient, "PARTIALLY" if more searching
            is needed, or None if the check failed (timeout/error).
        """
        combined_check = "\n---\n".join(relevant_contexts)
        completeness_prompt = COMPLETENESS_PROMPT_TEMPLATE.format(
            question=user_question,
            context=combined_check[:COMPLETENESS_CONTEXT_LIMIT],
        )
        try:
            check_res = await asyncio.wait_for(
                self.llm.ainvoke(completeness_prompt), timeout=COMPLETENESS_CHECK_TIMEOUT
            )
            check_raw = str(check_res.content).strip().upper()
            # Extract just the first word, strip markdown formatting (e.g. **FULLY**)
            first_word = check_raw.split()[0].strip("*_#.") if check_raw else "PARTIALLY"
            logger.info(f"Reasoner: Completeness check raw='{check_raw[:40]}' -> parsed='{first_word}'")
            # Default to PARTIAL unless the word clearly contains "FULL".
            # This is a safety-first approach: better to search more than miss info.
            if "FULL" not in first_word:
                logger.info("Reasoner: Context is not FULLY complete, searching for more info")
                return "PARTIALLY"
            return "FULLY"
        except Exception as e:
            logger.warning(f"Reasoner: Completeness check failed: {e}, proceeding to answer")
            return None

    async def _synthesize_answer(self, user_question: str, relevant_contexts: List[str]) -> AIMessage:
        """Generate a grounded answer using only grader-approved contexts.

        Uses a strict anti-hallucination prompt to ensure the answer
        is derived solely from the retrieved context.
        """
        combined = "\n---\n".join(relevant_contexts)
        answer_prompt = [
            SystemMessage(content=ANSWER_SYSTEM_PROMPT),
            HumanMessage(content=user_question),
            SystemMessage(content=f"Retrieved Context:\n{combined}"),
        ]
        response = await self.llm.ainvoke(answer_prompt)
        strip_tool_calls(response)
        return response

    async def _build_search_response(
        self, user_question: str, past_queries: List[str], relevant_contexts: List[str]
    ) -> AIMessage:
        """Generate an LLM response that calls the retrieve_documents tool.

        Constructs a prompt that includes past failed queries so the LLM
        avoids repeating them, then falls back to synthetic tool calls
        if the LLM refuses to use tools.
        """
        # Build a search instruction that tells the LLM what already failed or what's missing
        search_instruction = SEARCH_SYSTEM_PROMPT
        if past_queries:
            past_list = ", ".join([f'"{q}"' for q in past_queries])
            if relevant_contexts:
                found_preview = relevant_contexts[-1][:FOUND_PREVIEW_LIMIT]
                search_instruction += SEARCH_PARTIAL_ADDENDUM.format(
                    past_queries=past_list, found_preview=found_preview
                )
            else:
                search_instruction += SEARCH_FAILED_ADDENDUM.format(past_queries=past_list)
        search_prompt = [
            SystemMessage(content=search_instruction),
            HumanMessage(content=user_question),
        ]

        # Bind tool spec to LLM so it can emit tool_calls in the response.
        # Some vLLM deployments disable auto tool choice (--enable-auto-tool-choice not set),
        # which causes a 400 BadRequestError. In that case, skip straight to the synthetic fallback.
        response = None
        try:
            response = await self.llm.bind_tools(self.tools_spec).ainvoke(search_prompt)

            # Fallback: if the LLM refuses to use tools, prompt it more aggressively
            if not response.tool_calls:
                force_prompt = search_prompt + [HumanMessage(content=SEARCH_FORCE_NUDGE)]
                response = await self.llm.bind_tools(self.tools_spec).ainvoke(force_prompt)
        except Exception as e:
            if "tool choice" in str(e).lower() or "400" in str(e):
                logger.warning(f"bind_tools not supported by this vLLM deployment ({e}), using synthetic tool call.")
            else:
                raise

        # Last resort: create a synthetic tool call using the raw question
        # This ensures we always attempt at least one retrieval
        if not response or not response.tool_calls:
            logger.warning("Reasoner: Model refused tool call, creating synthetic search")
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "retrieve_documents",
                        "args": {"query": user_question},
                        "id": "forced_search",
                        "type": "tool_call",
                    }
                ],
            )

        return response

    async def reasoner(self, state: AgentState) -> Dict[str, Any]:
        """Central decision node. Called after START and after each grader verdict.

        Decision logic:
        1. If relevant context found + FULLY complete -> answer now
        2. If relevant context found + PARTIALLY complete -> search again
        3. If no relevant context yet -> search with new keywords
        4. If MAX_SEARCHES hit -> answer with whatever was found (or 'not found')
        """
        search_count = state.get("search_count", 0)
        relevance = state.get("relevance", "no")
        context_pool = state.get("context_pool", [])
        relevant_contexts = state.get("relevant_contexts", [])
        user_question = str(state["messages"][0].content)
        logger.info(
            f"Reasoner: search_count={search_count}, relevance={relevance}, "
            f"all_contexts={len(context_pool)}, relevant_contexts={len(relevant_contexts)}"
        )

        # DECISION 1: Should we answer now (no more searching)?
        hit_limit = search_count >= MAX_SEARCHES
        has_relevant = relevance == "yes" and len(relevant_contexts) > 0

        # Completeness check: only runs on the FIRST relevant hit (search_count < 2)
        # to decide if multi-part questions need more searching.
        # After 2 searches, we skip this check and answer with what we have.
        completeness_verdict = None
        if has_relevant and not hit_limit and search_count < 2:
            completeness_verdict = await self._check_completeness(user_question, relevant_contexts)
            if completeness_verdict == "PARTIALLY":
                has_relevant = False  # Force another search

        should_answer = hit_limit or has_relevant

        if should_answer:
            logger.info(
                f"Reasoner: ANSWERING (limit={search_count >= MAX_SEARCHES}, relevant={relevance}, "
                f"relevant_ctx_count={len(relevant_contexts)})"
            )

            # HALLUCINATION GUARD:
            # If NO context was graded relevant, do NOT call the LLM.
            if not relevant_contexts:
                logger.warning("Reasoner: ZERO relevant contexts after all searches. Returning hard 'not found'.")
                return {
                    "messages": [AIMessage(content=NOT_FOUND_MESSAGE)],
                    "completeness_verdict": completeness_verdict or "",
                }

            response = await self._synthesize_answer(user_question, relevant_contexts)
            return {
                "messages": [response],
                "completeness_verdict": completeness_verdict or "",
            }

        # DECISION 2: Search for information.
        past_queries = state.get("past_queries", [])
        logger.info(f"Reasoner: SEARCHING (attempt will be {search_count + 1}), past_queries={past_queries}")

        response = await self._build_search_response(user_question, past_queries, relevant_contexts)
        return {
            "messages": [response],
            "completeness_verdict": completeness_verdict or "",
        }

    async def tool_executor(self, state: AgentState) -> Dict[str, Any]:
        """Generic MCP tool dispatcher — executes whatever tool the LLM chose.

        Adding a new tool to the MCP server is all you need; this node
        routes any tool_call to session.call_tool(name, args) automatically.
        Returns the tool result and increments search_count by 1.
        """
        tool_call = cast(AIMessage, state["messages"][-1]).tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        logger.info(f"ToolExecutor: calling '{tool_name}' with args={tool_args}")
        try:
            res = await asyncio.wait_for(
                self.session.call_tool(tool_name, tool_args),
                timeout=RETRIEVAL_TIMEOUT,
            )
            content = res.content[0].text  # type: ignore[union-attr]
        except Exception as e:
            content = f"Error during {tool_name}: {str(e)}"

        search_query = tool_args.get("query", str(tool_args))
        return {
            "messages": [ToolMessage(content=content, tool_call_id=tool_call["id"])],
            "context_pool": [content],  # Keeps ALL retrievals (even grader-rejected) for log inspection
            "search_count": 1,  # Additive: LangGraph adds this to the running total
            "past_queries": [search_query],  # Track for retry diversity
        }

    async def grader_node(self, state: AgentState) -> Dict[str, Any]:
        """Judges whether the latest retrieval is relevant to the question.

        YES -> promotes the text to relevant_contexts (used for final answer).
        NO  -> adds a hint message to try different keywords.
        On timeout/error -> defaults to YES to avoid losing good content.
        """
        user_q = state["messages"][0].content
        last_message = state["messages"][-1]
        last_retrieval = last_message.content if hasattr(last_message, "content") else ""

        # Deduplication: if the same content was retrieved in a previous attempt,
        # skip the LLM grading call entirely and force a different search strategy.
        prev_retrievals = state.get("context_pool", [])[:-1]  # all but the current retrieval
        current_sig = content_hash(last_retrieval[:500])
        prev_sigs = {content_hash(r[:500]) for r in prev_retrievals}
        if current_sig in prev_sigs:
            logger.warning("Grader: Duplicate retrieval detected — skipping LLM call, forcing new strategy")
            return {
                "relevance": "no",
                "messages": [SystemMessage(content=GRADER_DUPLICATE_HINT)],
            }

        # Split the retrieval blob into individual chunks for per-chunk grading.
        # This prevents a single off-topic chunk from causing the entire batch to be
        # rejected — each chunk is scored independently and only relevant ones are kept.
        CHUNK_SEP = "\n\n---\n\n"
        chunks = [c.strip() for c in last_retrieval.split(CHUNK_SEP) if c.strip()]

        relevant_chunks: List[str] = []
        try:
            if len(chunks) <= 1:
                # Single chunk: use simple YES/NO grader (avoids the overhead of numbered format)
                grader_prompt = GRADER_PROMPT_TEMPLATE.format(
                    question=user_q,
                    text=(chunks[0] if chunks else last_retrieval)[:GRADER_TEXT_LIMIT],
                )
                res = await asyncio.wait_for(self.llm.ainvoke(grader_prompt), timeout=GRADER_TIMEOUT)
                raw = str(res.content).strip()
                logger.info(f"Grader (single-chunk) raw: '{raw[:80]}'")
                if not raw:
                    logger.warning("Grader returned empty response, defaulting to YES")
                    relevant_chunks = chunks
                elif raw.split()[0].lower().startswith("yes"):
                    relevant_chunks = chunks
            else:
                # Multiple chunks: one LLM call scores all chunks at once.
                # The LLM returns the indices of relevant chunks (e.g. "1, 3") or "NONE".
                numbered = "\n\n".join(f"[{i + 1}]\n{chunk[:GRADER_CHUNK_LIMIT]}" for i, chunk in enumerate(chunks))
                multi_prompt = MULTI_CHUNK_GRADER_PROMPT.format(
                    question=user_q,
                    n=len(chunks),
                    passages=numbered,
                )
                res = await asyncio.wait_for(self.llm.ainvoke(multi_prompt), timeout=GRADER_TIMEOUT)
                raw = str(res.content).strip()
                logger.info(f"Grader (multi-chunk, n={len(chunks)}) raw: '{raw[:120]}'")
                if raw and raw.upper() != "NONE":
                    for token in re.split(r"[,\s]+", raw):
                        if token.isdigit():
                            idx = int(token) - 1
                            if 0 <= idx < len(chunks):
                                relevant_chunks.append(chunks[idx])
                logger.info(f"Grader: {len(relevant_chunks)}/{len(chunks)} chunks passed")
        except Exception as e:
            logger.error(f"Grader error/timeout: {e}")
            # On timeout, assume all chunks are relevant to avoid losing good content
            relevant_chunks = chunks
            logger.info("Grader: TIMEOUT, keeping all chunks")

        is_relevant = len(relevant_chunks) > 0
        logger.info(f"Grader Verdict: {'yes' if is_relevant else 'no'}")

        result: Dict[str, Any] = {
            "relevance": "yes" if is_relevant else "no",
            # On NO: inject a hint so the reasoner knows to change strategy
            "messages": ([] if is_relevant else [SystemMessage(content=GRADER_REJECT_HINT)]),
        }
        # Only grader-approved chunks go into relevant_contexts, not the full blob.
        # This keeps the final answer grounded in the specific relevant passages.
        if is_relevant:
            result["relevant_contexts"] = relevant_chunks

        return result

    @staticmethod
    def should_continue(state: AgentState) -> str:
        """Edge router after reasoner: decides whether to retrieve or stop."""
        messages = state["messages"]
        last_message = messages[-1]
        search_count = state.get("search_count", 0)

        # HARD SAFETY NET #1: search_count limit
        if search_count >= MAX_SEARCHES:
            logger.info(f"should_continue: STOP (search_count={search_count} >= {MAX_SEARCHES})")
            return END

        # Only continue to tool_executor if there are actual tool calls
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tool_executor"

        return END

    def build_graph(self):
        """Construct and compile the LangGraph state machine."""
        # Graph topology: START -> reasoner --(tool_calls?)--> tool_executor -> grader -> reasoner
        #                                  \--(no tool_calls)--> END
        workflow = StateGraph(AgentState)
        workflow.add_node("reasoner", self.reasoner)
        workflow.add_node("tool_executor", self.tool_executor)
        workflow.add_node("grader", self.grader_node)

        workflow.add_edge(START, "reasoner")
        workflow.add_conditional_edges("reasoner", self.should_continue)
        workflow.add_edge("tool_executor", "grader")  # Every tool result is graded
        workflow.add_edge("grader", "reasoner")  # After grading, reasoner decides next step

        return workflow.compile()


# 3. LLM FACTORY


def create_llm() -> ChatOpenAI:
    """Build the ChatOpenAI client from environment config.

    Centralised here so callers (or future multi-agent setups) can
    override model, temperature, or provider without touching the agent.
    """
    return ChatOpenAI(
        base_url=config.VLLM_BASE_URL,
        model=config.GEN_MODEL,
        api_key=SecretStr("na"),
        temperature=0,
        timeout=LLM_REQUEST_TIMEOUT,
        max_retries=2,
    )


# 4. PUBLIC ENTRY POINT


async def run_rag_agent(query: str, file_paths: Optional[List[str]] = None) -> AsyncGenerator[str, None]:
    """Connect to MCP, optionally ingest files, and run the RAG agent graph.

    Yields trace events and the final answer as formatted strings.
    Retries on transient SSE/TaskGroup errors.
    """
    mcp_headers = {"Connection": "keep-alive"}
    MAX_SESSION_RETRIES = 4
    RETRY_DELAY = 3.0  # seconds; doubles each attempt

    for attempt in range(1, MAX_SESSION_RETRIES + 1):
        try:
            async with sse_client(url=config.MCP_URL, headers=mcp_headers) as (  # type: ignore[attr-defined]
                read_stream,
                write_stream,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await asyncio.wait_for(session.initialize(), timeout=SESSION_INIT_TIMEOUT)

                    # STEP 1: INITIAL DATA SYNC
                    if file_paths:
                        async for event in ingest_files(session, file_paths):
                            yield event

                    # STEP 2: BUILD AGENT (tools auto-discovered from MCP)
                    llm = create_llm()
                    agent = await RAGAgent.create(session=session, llm=llm)
                    agent_app = agent.build_graph()

                    # HARD SAFETY NET: LangGraph recursion limit.
                    # Each search cycle = 3 steps (reasoner + tool_executor + grader).
                    # 3 cycles * 3 steps + 5 buffer = 14 max steps before LangGraph aborts.
                    recursion_limit = (MAX_SEARCHES * 3) + 5

                    # STEP 3: STREAM RESULTS
                    initial_input = {
                        "messages": [HumanMessage(content=query)],
                        "context_pool": [],
                        "relevant_contexts": [],
                        "search_count": 0,
                        "past_queries": [],
                        "completeness_verdict": "",
                    }

                    async for event in stream_agent_events(agent_app, initial_input, recursion_limit):
                        yield event
                    return  # Completed successfully — exit retry loop

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            # ExceptionGroup (raised by anyio's TaskGroup in Python 3.11+) inherits from
            # Exception, so it is caught here. KeyboardInterrupt/SystemExit are already
            # re-raised above. Log inner sub-exceptions for debugging.
            inner = getattr(e, "exceptions", None)
            inner_str = f" | inner: {[type(x).__name__ + ': ' + str(x) for x in inner]}" if inner else ""
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            if attempt < MAX_SESSION_RETRIES:
                logger.warning(
                    f"Session error (attempt {attempt}/{MAX_SESSION_RETRIES}): "
                    f"{type(e).__name__}: {e}{inner_str}. Retrying in {delay:.0f}s..."
                )
                await asyncio.sleep(delay)
                continue
            logger.error(f"Crosstalk/Session Error: {type(e).__name__}: {e}{inner_str}")
            yield "❌ System Error: Session error or timeout. Please try again later."
