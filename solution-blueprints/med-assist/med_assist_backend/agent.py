# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    ChatMessage,
    JobContext,
    StopResponse,
    cli,
    llm,
    room_io,
)
from livekit.plugins import openai, silero
from prompts import (  # type: ignore[attr-defined]
    ALERT_SYSTEM_PROMPT,
    ALERT_USER_PROMPT_TEMPLATE,
    REPORT_SYSTEM_PROMPT,
    REPORT_USER_PROMPT_TEMPLATE,
)
from pydantic import BaseModel, Field, RootModel, ValidationError
from settings import settings

from utils import init_llm  # type: ignore[attr-defined]

logger = logging.getLogger("consultation-agent")
logger.setLevel(logging.INFO)


# Structured output schema for alert detection (LLM response)
class AlertItem(BaseModel):
    """Single medical alert from LLM."""

    alert_type: str = Field(..., description="One of drug_interaction, allergy_concern, etc.")
    severity: str = Field(..., description="critical, warning, or info")
    title: str = Field(..., description="Short heading for the alert")
    evidence: str = Field(..., description="Description and recommendation")
    entities: list[str] = Field(default_factory=list, description="Normalized key terms, e.g. drug names")


class AlertsStructuredOutput(RootModel[list[AlertItem]]):
    """Structured output: JSON array of AlertItem. Use model_validate_json(cleaned) then .root for the list."""


class ConsultationAgent(Agent):
    """Voice consultation agent: transcription (STT → data "transcript") and report generation on data
    "request_report" → LLM → data "report". Speaker is determined by dominant speaker."""

    REPORT_TOPIC_REQUEST: str = "report_request"
    REPORT_TOPIC_RESPONSE: str = "report"
    REPORT_REQUEST_TYPE: str = "request_report"
    ALERT_TOPIC: str = "alert"

    def __init__(self, room: rtc.Room, llm_instance: openai.llm.LLM) -> None:
        """Initialize consultation agent with LiveKit room and LLM client.

        Args:
            room (rtc.Room): LiveKit RTC room used for media and data channels.
            llm_instance (openai.llm.LLM): LLM client used for both report generation and alert detection.
        """
        super().__init__(
            instructions="You are a transcription logger. Do not respond.",
            stt=openai.STT(
                model=settings.stt_model,
                base_url=settings.stt_base_url.encoded_string(),
                api_key=settings.stt_api_key.get_secret_value(),
                language="en",
                detect_language=False,
            ),
        )
        self._room = room
        self._last_speaker_identity: str | None = None
        self._report_llm = llm_instance
        self._transcript_buffer: list[dict] = []
        self._sent_alert_signatures: set[str] = set()
        self._alert_check_interval: int = 3
        self._alert_window_size: int = 20

        @room.on("active_speakers_changed")
        def _on_active_speakers(speakers: list[rtc.Participant]) -> None:
            """Track the most recently active speaker in the room."""
            if speakers:
                self._last_speaker_identity = speakers[0].identity

        @room.on("data_received")
        def _on_data(data_packet: rtc.DataPacket) -> None:
            """Dispatch incoming data packets that request a consultation report."""
            if self._is_report_request(data_packet):
                asyncio.create_task(self._handle_report_request(data_packet))

    async def on_user_turn_completed(self, chat_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        """Handle completion of a user speaking turn.

        Extracts the ASR transcript from the message, publishes it as a data packet
        to the room, appends it to the internal transcript buffer, and schedules
        alert detection when needed.

        Args:
            chat_ctx (llm.ChatContext): Conversation context for the current agent session.
            new_message (llm.ChatMessage): Newly received user message containing ASR text.

        Raises:
            StopResponse: Always raised at the end of handling to stop further LLM generation.

        """
        user_transcript = (new_message.text_content or "").split("<asr_text>", 1)[-1]

        if not user_transcript:
            raise StopResponse()

        identity = self._last_speaker_identity or getattr(new_message, "participant_identity", "user")
        ts = datetime.now(timezone.utc).isoformat()

        payload = json.dumps(
            {
                "type": "transcript",
                "identity": identity,
                "text": user_transcript,
                "timestamp": ts,
            }
        )
        await self._room.local_participant.publish_data(
            payload.encode("utf-8"),
            topic="transcript",
        )

        self._transcript_buffer.append({"identity": identity, "text": user_transcript})

        if len(self._transcript_buffer) % self._alert_check_interval == 0:
            asyncio.create_task(self._check_and_publish_alerts())

        logger.info("%s: %s", identity, user_transcript[:80], extra={"timestamp": ts})
        raise StopResponse()

    def _is_report_request(self, data_packet: rtc.DataPacket) -> bool:
        """Determine whether an incoming data packet requests a report.

        The method first checks the packet topic, and if absent, inspects the JSON
        payload for the expected request type.

        Args:
            data_packet (rtc.DataPacket): LiveKit data packet received from the room.

        Returns:
            True if the packet represents a report request, otherwise False.

        """
        if data_packet.topic == self.REPORT_TOPIC_REQUEST:
            return True

        if data_packet.topic is not None:
            return False
        try:
            d = json.loads(data_packet.data.decode("utf-8"))
            return d.get("type") == self.REPORT_REQUEST_TYPE

        except Exception as exc:
            logger.exception("Failed to parse data packet as report request", exc_info=exc)
            return False

    async def _generate_report(self, transcript: str) -> str:
        """Generate a structured consultation report from a transcript.

        Builds an LLM chat context using report prompts and streams the response,
        concatenating chunks into a final report string.

        Args:
            transcript (str): Plain-text transcript of the consultation.

        Returns:
            The generated report text, trimmed of surrounding whitespace.

        """
        text = (transcript or "").strip() or "(empty transcript)"

        logger.info("Generating report from transcript (%d chars)", len(text))

        ctx = llm.ChatContext(
            items=[
                ChatMessage(role="system", content=[REPORT_SYSTEM_PROMPT]),
                ChatMessage(role="user", content=[REPORT_USER_PROMPT_TEMPLATE + text]),
            ]
        )

        parts = []

        async for chunk in self._report_llm.chat(chat_ctx=ctx):

            if chunk.delta and chunk.delta.content:
                parts.append(chunk.delta.content)

        report = "".join(parts).strip()
        logger.info("Report generation complete (%d chars)", len(report))
        return report

    async def _handle_report_request(self, data_packet: rtc.DataPacket) -> None:
        """Handle an incoming report request data packet.

        Parses the request payload, invokes report generation, and publishes
        the resulting report back to the room as a data packet.

        Because LiveKit reliable delivery is best-effort (no server-side buffering,
        limited retransmissions), the frontend may retry the same request_id.
        This method processes every incoming request regardless — the frontend
        deduplicates by request_id on its side.

        Args:
            data_packet (rtc.DataPacket): LiveKit data packet that triggered the report request.

        Returns:
            None. Errors are logged and converted into an error message in the report.

        """
        try:
            payload = json.loads(data_packet.data.decode("utf-8"))
        except Exception as exc:
            logger.exception("Failed to decode report request payload", exc_info=exc)
            return None

        if payload.get("type") != self.REPORT_REQUEST_TYPE:
            return None

        transcript = payload.get("transcript") or ""
        request_id = payload.get("request_id") or ""
        sender = data_packet.participant.identity if data_packet.participant else None

        logger.info(
            "Report requested by %s (request_id=%s, transcript_len=%d)",
            sender,
            request_id,
            len(transcript),
        )

        try:
            report = await self._generate_report(transcript)
        except Exception as e:
            logger.exception("Report generation failed (request_id=%s)", request_id)
            report = f"Error generating report: {e!s}"

        out = json.dumps({"type": "report", "report": report, "request_id": request_id})
        out_bytes = out.encode("utf-8")

        logger.info(
            "Publishing report to room (request_id=%s, payload_bytes=%d, reliable=True)",
            request_id,
            len(out_bytes),
        )

        await self._room.local_participant.publish_data(
            out_bytes,
            topic=self.REPORT_TOPIC_RESPONSE,
            reliable=True,
        )

        logger.info(
            "Report published successfully (request_id=%s) at %s",
            request_id,
            datetime.now(timezone.utc).isoformat(),
        )
        return None

    async def _detect_alerts(self) -> list[dict]:
        """Run LLM-based detection of medical alerts over recent transcript window.

        Uses the internal transcript buffer to build a sliding window of recent
        utterances, sends it to the LLM with alert prompts, and post-processes
        structured output into a list of new alerts, deduplicated by signature.

        Returns:
            List of alert dictionaries ready to be published to the room.

        """
        if len(self._transcript_buffer) < 2:
            return []

        transcript_text = "\n".join(
            [f"{e['identity']}: {e.get('text', '')}" for e in self._transcript_buffer[-self._alert_window_size :]]
        )

        parts = []

        async for chunk in self._report_llm.chat(
            chat_ctx=llm.ChatContext(
                items=[
                    ChatMessage(role="system", content=[ALERT_SYSTEM_PROMPT]),
                    ChatMessage(role="user", content=[ALERT_USER_PROMPT_TEMPLATE + transcript_text]),
                ]
            )
        ):

            if chunk.delta and chunk.delta.content:
                parts.append(chunk.delta.content)

        raw = "".join(parts).strip()

        try:
            alert_items = self._parse_alerts_structured(raw)

        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            logger.warning("Alert structured output parse failed: %s", e, extra={"raw_preview": raw[:200]})
            return []

        new_alerts: list[dict] = []

        for item in alert_items:

            alert_type = (item.alert_type or "").strip()
            severity = (item.severity or "info").strip().lower()

            if severity not in ("critical", "warning", "info"):
                severity = "info"

            title = (item.title or "Alert").strip()
            evidence = (item.evidence or "").strip()
            entities = [str(e).strip().lower() for e in (item.entities or []) if e]

            if not title and not evidence:
                continue

            sig = self._alert_signature(severity, alert_type, entities)

            if sig in self._sent_alert_signatures:
                continue

            self._sent_alert_signatures.add(sig)
            new_alerts.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": severity,
                    "title": title,
                    "evidence": evidence,
                }
            )

        return new_alerts

    async def _check_and_publish_alerts(self) -> None:
        """Detect new alerts and publish them as LiveKit data packets."""
        try:
            new_alerts = await self._detect_alerts()

            for alert in new_alerts:
                payload = json.dumps(alert)
                await self._room.local_participant.publish_data(
                    payload.encode("utf-8"),
                    topic=self.ALERT_TOPIC,
                )
                logger.info("Alert published: %s", alert.get("title"), extra={"severity": alert.get("severity")})

        except Exception as exc:
            logger.exception("Alert detection failed: %s", exc)

    @staticmethod
    def _alert_signature(severity: str, alert_type: str, entities: list[str]) -> str:
        """Build a stable signature string for an alert.

        Args:
            severity (str): Normalized severity level (critical, warning, or info).
            alert_type (str): High-level category of the alert.
            entities (list[str]): List of normalized entity strings associated with the alert.

        Returns:
            A deterministic signature string used for deduplication.

        """
        normalized = ",".join(sorted((e or "").strip().lower() for e in (entities or []) if e))
        return f"{severity}:{alert_type}:{normalized}"

    @staticmethod
    def _parse_alerts_structured(raw: str) -> list[AlertItem]:
        """Parse LLM response into a list of AlertItem instances.

        Strips optional Markdown code fences from the raw string and validates
        the remaining JSON using the Pydantic `AlertsStructuredOutput` model.

        Args:
            raw (str): Raw LLM response, possibly wrapped in Markdown fences.

        Returns:
            list[AlertItem]: Parsed and validated list of alert items.

        Raises:
            ValueError: If the payload cannot be validated as alerts.
            json.JSONDecodeError: If the cleaned payload is not valid JSON.
            ValidationError: If Pydantic validation of the structured output fails.

        """
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        parsed = AlertsStructuredOutput.model_validate_json(cleaned)
        return list(parsed.root)


server = AgentServer(
    ws_url=settings.livekit_ws_url.encoded_string(),
    api_key=settings.livekit_api_key.get_secret_value(),
    api_secret=settings.livekit_api_secret.get_secret_value(),
)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("Job received, connecting to room %s", ctx.room.name)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to room %s", ctx.room.name)

    llm_instance = await init_llm(
        api_key=settings.llm_api_key.get_secret_value(), base_url=settings.llm_url.encoded_string()
    )

    session = AgentSession(
        vad=silero.VAD.load(),
        preemptive_generation=True,
    )

    await session.start(
        agent=ConsultationAgent(room=ctx.room, llm_instance=llm_instance),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            text_output=True,
            audio_output=False,
            close_on_disconnect=False,
        ),
    )
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
