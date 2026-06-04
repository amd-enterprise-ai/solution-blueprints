# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import inspect
import json
import logging
import re
import sys
import time
from typing import Any, AsyncIterable

import httpx
import livekit.plugins.openai.tts as livekit_tts
import openai as openai_sdk
from bss_gateway_client import BSSGatewayClient
from ingest_chromadb import main as ingest_main
from libre_desk_client import LibreDeskClient
from livekit import agents, rtc
from livekit.plugins import openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from settings import settings
from system_prompts import SYSTEM_INSTRUCTIONS
from vector_store import ChromaHybridStore

MAX_DOC_CHARS = 1500
MAX_TOTAL_CONTEXT_CHARS = 4000

logger = logging.getLogger(__name__)

# ============ PATCH TTS TIMEOUT ============

try:
    target_class = livekit_tts.ChunkedStream
    original_method = target_class._run

    if not inspect.iscoroutinefunction(original_method):
        raise AttributeError("_run is not a coroutine, patch may be incompatible")

    async def patched_run(self, output_emitter):
        logger.info(f"PATCHED TTS timeout: read=90.0s, connect={self._conn_options.timeout}s")

        oai_stream = self._tts._client.audio.speech.with_streaming_response.create(
            input=self.input_text,
            model=self._opts.model,
            voice=self._opts.voice,
            response_format=self._opts.response_format,
            speed=self._opts.speed,
            instructions=self._opts.instructions or openai_sdk.omit,
            timeout=httpx.Timeout(90.0, connect=self._conn_options.timeout),
        )

        try:
            async with oai_stream as stream:
                output_emitter.initialize(
                    request_id=stream.request_id or "",
                    sample_rate=livekit_tts.SAMPLE_RATE,
                    num_channels=livekit_tts.NUM_CHANNELS,
                    mime_type=f"audio/{self._opts.response_format}",
                )
                async for data in stream.iter_bytes():
                    output_emitter.push(data)
            output_emitter.flush()
        except openai_sdk.APITimeoutError:
            raise livekit_tts.APITimeoutError() from None
        except openai_sdk.APIStatusError as e:
            raise livekit_tts.APIStatusError(
                e.message, status_code=e.status_code, request_id=e.request_id, body=e.body
            ) from None
        except Exception as e:
            raise livekit_tts.APIConnectionError() from e

    livekit_tts.ChunkedStream._run = patched_run
    logger.info("PATCHED TTS timeout applied successfully.")

except Exception as e:
    logger.critical(
        f"CRITICAL: Failed to apply TTS timeout patch. "
        f"The app may crash or use default timeouts. "
        f"Check livekit version compatibility. Error: {e}"
    )
# ===========================================

server = agents.AgentServer()


class QwenASRWrapper(openai.STT):
    async def recognize(self, *args, **kwargs):
        result = await super().recognize(*args, **kwargs)
        if result and result.alternatives:
            for alt in result.alternatives:
                clean_match = re.search(r"<asr_text>(.*)", alt.text)
                if clean_match:
                    alt.text = clean_match.group(1).strip()
                else:
                    alt.text = re.sub(r"^language \w+", "", alt.text).strip()

        logger.debug(f"STT result: {result}")

        return result


class Assistant(agents.Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_INSTRUCTIONS)
        self.store = ChromaHybridStore() if settings.chroma_url else None
        logger.info("Storage initialized")
        self.bssgateway_client = BSSGatewayClient() if settings.bssgateway_url else None
        logger.info("BSS Gateway initialized")
        self.libredesk_client = LibreDeskClient() if settings.libredesk_url else None
        logger.info("Libredesk initialized")

    async def tts_node(self, text: AsyncIterable[str], model_settings) -> AsyncIterable[rtc.AudioFrame]:
        async def logged_text():
            full_text = []
            async for chunk in text:
                full_text.append(chunk)
                yield chunk
            logger.info(f"TTS full text: {''.join(full_text)}")

        async for frame in agents.Agent.default.tts_node(self, logged_text(), model_settings):
            yield frame

    @agents.function_tool
    async def get_user_by_pass_phrase(self, context: agents.RunContext, pass_phrase: str) -> dict:
        """
        Retrieve a unique user using a secret pass phrase.

        Args:
            context: The execution context containing dependencies.
            pass_phrase: The user's secret phrase used for identification.
                        IMPORTANT: Format as a single lowercase word without spaces (e.g., 'milkyway').
                        IMPORTANT: DO NOT invent or placeholder this value.
                        If the user has not provided a phrase yet, DO NOT call this tool.
                        Instead, ask the user to provide it.

        Returns:
            dict: An object containing user_id, first_name, and last_name.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            normalized = "".join(char.lower() for char in pass_phrase if char.isalnum())
            result = await self.bssgateway_client.get_user_by_phrase(normalized)
            room = agents.get_job_context().room

            if not room.remote_participants:
                return {"error": "User has disconnected from the call."}

            participant_identity = next(iter(room.remote_participants))
            await room.local_participant.perform_rpc(
                destination_identity=participant_identity,
                method="userAuthenticated",
                payload=json.dumps({"UserName": f"{result.first_name} {result.last_name}"}),
            )

            return result.model_dump()
        except Exception as e:
            logger.exception(f"Failed to find user by pass phrase: {e}")
            return {"error": "User not found. Please ask the user to provide their pass phrase again."}

    @agents.function_tool
    async def get_user_role(self, context: agents.RunContext, user_id: str) -> Any:
        """
        Retrieve the role (e.g., 'admin', 'user') for a specific user ID.

        Args:
            context: The execution context containing dependencies.
            user_id: The unique identifier of the user.

        Returns:
            dict: A dictionary containing 'user_id' and the assigned 'role'.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            return await self.bssgateway_client.get_user_role(user_id)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving role for user '{user_id}'. {e}")
            return {"error": "Failed to retrieve user role."}

    @agents.function_tool
    async def get_user_plan_name(self, context: agents.RunContext, user_id: str) -> Any:
        """
        Retrieve the name of the current subscription plan for a specific user.

        Args:
            context: The execution context containing dependencies.
            user_id: The unique identifier of the user.

        Returns:
            dict: A dictionary containing 'user_id' and 'plan_name'.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            return await self.bssgateway_client.get_user_plan(user_id)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving plan name for user '{user_id}'. {e}")
            return {"error": "Failed to retrieve plan name."}

    @agents.function_tool
    async def add_extra_quota(
        self,
        context: agents.RunContext,
        user_id: str,
        plan: str,
        quota: int,
    ) -> Any:
        """
        Add extra quota to high_speed_quotas for a given user and plan.
        Args:
            context: Execution context.
            user_id: The unique identifier of the user.
            plan: Plan name (must match user's plan).
            quota: Amount of quota to add (>= 0).
        Returns:
            dict: Updated quota object.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            if quota <= 0:
                return {"error": "Failed to add extra quota: Amount of quota to add must be more than 0"}

            return await self.bssgateway_client.add_extra_quota(user_id, plan, quota)
        except Exception as e:
            logger.exception(f"Error occurred while adding extra quota for user '{user_id}'. {e}")
            return {"error": "Failed to add extra quota."}

    @agents.function_tool
    async def get_plan_quotas(self, context: agents.RunContext, user_id: str, plan: str) -> Any:
        """
        Retrieve high_speed_quotas for a given user and plan.
        Args:
            context: Execution context.
            user_id: The unique identifier of the user.
            plan: Plan name (must match user's plan).
        Returns:
            dict: Object with user_id, plan_name, high_speed_quotas.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            return await self.bssgateway_client.get_plan_quotas(user_id, plan)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving plan quotas for user '{user_id}'. {e}")
            return {"error": "Failed to retrieve user's plan quotas."}

    @agents.function_tool
    async def get_balance(self, context: agents.RunContext, user_id: str) -> Any:
        """
        Retrieve current account balance for a given user from the Billing API.

        Args:
           context: The execution context containing dependencies.
           user_id: The unique identifier of the user.

        Returns:
           dict: A dictionary containing 'amount' (float) and 'currency' (str).
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            return await self.bssgateway_client.get_balance(user_id)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving account balance for user '{user_id}'. {e}")
            return {"error": "Failed to retrieve user's account balance."}

    @agents.function_tool
    async def get_payments(self, context: agents.RunContext, user_id: str) -> Any:
        """
        Retrieve payment history for a given user from the Billing API.

        Args:
            context: The execution context containing dependencies.
            user_id: The unique identifier of the user.

        Returns:
            list[dict]: A list of objects, each representing a transaction with details like date, amount.
        """
        if not self.bssgateway_client:
            return {"error": "BSS Gateway is not configured."}
        try:
            return await self.bssgateway_client.get_payments(user_id)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving payments history for user '{user_id}'. {e}")
            return {"error": "Failed to retrieve user payments history."}

    @agents.function_tool
    async def get_invoices(self, context: agents.RunContext, user_id: str) -> str:
        """
        Retrieve invoice history for a given user from the Billing API.

        Args:
         context: The execution context containing dependencies.
         user_id: The unique identifier of the user.

        Returns:
            str: A formatted string or JSON representation of issued invoices and their current statuses (e.g., 'paid', 'pending').
        """
        if not self.bssgateway_client:
            return "Failed to retrieve user invoices history: BSS Gateway is not configured."
        try:
            return await self.bssgateway_client.get_invoices(user_id)
        except Exception as e:
            logger.exception(f"Error occurred while retrieving invoices history for user '{user_id}'. {e}")
            return "Failed to retrieve user invoices history."

    @agents.function_tool
    async def escalate_to_support(self, context: agents.RunContext, user_id: str, issue: str) -> Any:
        """
        Escalate unresolved billing issue to support by creating a ticket in Libredesk.

        Creates a support ticket containing the user issue description and returns the metadata of the created ticket.

        Args:
            context: The execution context containing dependencies.
            user_id: The unique identifier of the user.
            issue: A string description of the billing problem provided by the user.

        Returns:
            dict: A dictionary containing the metadata of the created Libredesk ticket (e.g., ticket ID, status, and creation timestamp).
        """
        if not self.libredesk_client:
            return {"error": "Libredesk is not configured."}
        try:
            return await self.libredesk_client.create_ticket(
                title="Billing escalation",
                body=issue,
                customer=user_id,
            )
        except Exception as e:
            logger.exception(f"Failed to create support ticket for user '{user_id}'. {e}")
            return {"error": "Failed to create support ticket."}

    @agents.function_tool
    async def billing_docs_search(self, context: agents.RunContext, query: str) -> str:
        """
        Hybrid search in billing knowledge base.

        Args:
            context: The execution context containing dependencies.
            query: The specific search terms or question from the user regarding billing, invoices, or payments.

        Returns:
            str: A formatted block of text containing relevant documentation snippets to be used by the LLM for answering.
        """
        if not self.store:
            return "Failed to search info in billing knowledge base: ChromaDB is not configured."
        try:
            start_time = time.monotonic()

            if not query or not query.strip():
                return "Please provide a billing-related question."

            query = query.strip()
            try:
                results = await self.store.hybrid_search(query, k=4)
                for result in results:
                    logger.info(f"RFF Score: {result.get("rrf_score", -1)}\nDocument:{result.get("document")}\n")
                results = [r for r in results if r.get("rrf_score", 0) >= 0.03]
            except Exception as ex:
                logger.exception(f"Hybrid search failed. {ex}")
                return "Billing knowledge base is currently unavailable."

            if not results:
                return "I don't have relevant information about that topic."

            total_chars = 0
            context_parts = []

            for r in results:
                doc = r.get("document", "")
                if not doc:
                    continue

                # Truncate individual document
                doc = doc[:MAX_DOC_CHARS]

                if total_chars + len(doc) > MAX_TOTAL_CONTEXT_CHARS:
                    break

                context_parts.append(doc)
                total_chars += len(doc)

            if not context_parts:
                return "No relevant billing information found."

            context_text = "\n\n".join(context_parts)

            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.info(
                "billing_docs_search | query=%s | results=%d | latency=%dms",
                query,
                len(results),
                latency_ms,
            )

            return f"Context:\n{context_text}"
        except Exception as e:
            logger.exception(f"Billing docs search failed. {e}")
            return "Failed to search info in billing knowledge base."


def prewarm(proc: agents.JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    session = agents.AgentSession(
        stt=QwenASRWrapper(
            model=settings.stt_model,
            base_url=settings.stt_base_url,
            api_key=settings.stt_api_key,
            language="en",
        ),
        llm=openai.LLM(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        ),
        tts=openai.TTS(
            model=settings.tts_model,
            voice=settings.tts_voice,
            client=openai_sdk.AsyncClient(
                max_retries=0,
                base_url=settings.tts_base_url,
                api_key=settings.tts_api_key,
                http_client=httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=5.0),
                    follow_redirects=True,
                    limits=httpx.Limits(max_connections=50, max_keepalive_connections=50, keepalive_expiry=120),
                ),
            ),
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,
        conn_options=agents.voice.agent_session.SessionConnectOptions(
            stt_conn_options=agents.types.APIConnectOptions(timeout=30.0),
            llm_conn_options=agents.types.APIConnectOptions(timeout=30.0),
            tts_conn_options=agents.types.APIConnectOptions(timeout=90.0),
        ),
        max_tool_steps=10,
    )

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.info(f"Participant {participant.identity} disconnected")
        asyncio.create_task(session.aclose())

    @session.on("error")
    def on_session_error(error):
        logger.error(f"Error session: {error}")
        asyncio.create_task(session.aclose())

    @session.on("function_tools_executed")
    def on_function_tools_executed(event: agents.FunctionToolsExecutedEvent) -> None:
        room = agents.get_job_context().room
        participant_identity = next(iter(room.remote_participants))

        async def call_rpc():
            for call, output in event.zipped():
                duration_ms = (output.created_at - call.created_at) * 1000
                data = {
                    "Function": call.name,
                    "Arguments": call.arguments,
                    "Output": output.output,
                    "IsError": output.is_error,
                    "DurationMs": round(duration_ms, 2),
                }
                await room.local_participant.perform_rpc(
                    destination_identity=participant_identity,
                    method="functionToolsExecuted",
                    payload=json.dumps(data, ensure_ascii=False),
                )

                logger.info(f"Tool Log: {data}")

        asyncio.create_task(call_rpc())

    await ctx.connect()
    logger.info("WebSocket registered for a task.")

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=agents.room_io.RoomOptions(
            text_input=True,
            text_output=True,
            audio_input=True,
            audio_output=True,
        ),
    )
    logger.info("Session started.")
    await session.say(
        "Hello. How can I assist you with your account or service today?",
        allow_interruptions=False,
    )


def extract_ingest_args(argv):
    custom_data_path = None
    force_ingest = False
    append_ingest = False

    cleaned_argv = [argv[0]]
    i = 1

    while i < len(argv):
        arg = argv[i]

        if arg == "--ingest-file":
            if i + 1 >= len(argv):
                raise ValueError("Expected path after --ingest-file")
            custom_data_path = argv[i + 1]
            i += 2
            continue

        if arg.startswith("--ingest-file="):
            custom_data_path = arg.split("=", 1)[1]
            i += 1
            continue

        if arg == "--force-ingest":
            force_ingest = True
            i += 1
            continue

        if arg == "--append-ingest":
            append_ingest = True
            i += 1
            continue

        cleaned_argv.append(arg)
        i += 1

    if force_ingest and append_ingest:
        raise ValueError("Arguments --force-ingest and --append-ingest cannot be used together")

    return custom_data_path, force_ingest, append_ingest, cleaned_argv


if __name__ == "__main__":
    custom_data_path, force_ingest, append_ingest, cleaned_argv = extract_ingest_args(sys.argv)

    asyncio.run(
        ingest_main(
            custom_data_path=custom_data_path,
            force=force_ingest,
            append=append_ingest,
        )
    )

    sys.argv = cleaned_argv
    agents.cli.run_app(server)
