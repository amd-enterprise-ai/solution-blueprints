# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Builder that runs the end-to-end monologue/podcast generation pipeline."""


import asyncio
import logging
from typing import Any, Iterable, Literal, Sequence

import jinja2
import ujson as json
from agent.chat_llm import ChatLLM
from core.models import Conversation, PdfMetadata, PodcastOutline, ServiceType, TaskStatus
from core.task_store import TaskStore
from domain.prompt_tracker import PromptTracker
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


class PodcastScenarioBuilder:
    """End-to-end runner for monologue and podcast flows."""

    def __init__(
        self,
        *,
        llm: ChatLLM,
        prompt_tracker: PromptTracker,
        prompt_templates: dict[str, str],
        task_store: TaskStore | None = None,
    ) -> None:
        """Initialize the podcast scenario builder.

        Args:
            llm (ChatLLM): ChatLLM instance for LLM queries.
            prompt_tracker (PromptTracker): Tracker for prompt/response history.
            prompt_templates (dict[str, str]): Dictionary mapping template names to template strings.
            task_store (TaskStore | None): Optional task store for status updates. Defaults to None.

        Returns:
            None
        """
        self.llm = llm
        self.prompt_tracker = prompt_tracker
        self.templates = {name: jinja2.Template(tpl, autoescape=True) for name, tpl in prompt_templates.items()}
        self.task_store = task_store

    async def _update_status(self, task_id: str, message: str, progress: float | None = None) -> None:
        """Update task status if task_store is available.

        Args:
            task_id (str): Task identifier.
            message (str): Status message.
            progress (float | None): Optional progress [0..1]. Defaults to None.
        """
        if self.task_store:
            await self.task_store.update_status(
                task_id, ServiceType.AGENT, TaskStatus.PROCESSING, message, progress=progress
            )

    async def run(
        self,
        *,
        kind: Literal["monologue", "podcast"],
        pdfs: Sequence[PdfMetadata],
        request: Any,
        task_id: str,
    ) -> Conversation:
        """Unified entrypoint: choose monologue or podcast flow by kind.

        Args:
            kind (Literal["monologue", "podcast"]): Type of flow to run.
            pdfs (Sequence[PdfMetadata]): Sequence of PDF metadata objects.
            request (Any): Request object containing flow-specific parameters.
            task_id (str): Task identifier for logging and tracking.

        Returns:
            Conversation: Generated conversation model.

        Raises:
            ValueError: If kind is not "monologue" or "podcast".
        """
        if kind == "monologue":
            return await self.run_monologue(pdfs=pdfs, request=request, task_id=task_id)
        if kind == "podcast":
            return await self.run_podcast(pdfs=pdfs, request=request, task_id=task_id)
        raise ValueError(f"Unsupported flow kind: {kind}")

    async def run_monologue(self, *, pdfs: Sequence[PdfMetadata], request: Any, task_id: str) -> Conversation:
        """Generate a monologue conversation from PDF documents.

        Args:
            pdfs (Sequence[PdfMetadata]): Sequence of PDF metadata objects to process.
            request (Any): Request object containing speaker name, guide, and PDF metadata.
            task_id (str): Task identifier for logging and tracking.

        Returns:
            Conversation: Generated monologue conversation model.

        Raises:
            ValueError: If both speaker_1_name and speaker_2_name are provided.
        """
        logger.info("Task %s: Starting monologue generation", task_id)
        await self._update_status(task_id, "Starting monologue generation")
        if request.speaker_1_name and request.speaker_2_name:
            raise ValueError("Only one speaker is allowed for monologue flow")

        logger.info("Task %s: Summarizing %d PDF(s)", task_id, len(pdfs))
        await self._update_status(task_id, f"Summarizing {len(pdfs)} PDF document(s)", progress=0.1)
        summarized = await self._summarize_pdfs(
            pdfs,
            template_name="summary_prompt",
        )

        documents = [f"Document: {pdf.filename}\n{pdf.summary}" for pdf in summarized]
        logger.info("Task %s: Generating monologue outline", task_id)
        await self._update_status(task_id, "Generating monologue outline", progress=0.3)
        try:
            raw_outline = await self._generate_raw_outline(
                documents="\n\n".join(documents),
                template_name="multi_doc_synthesis_prompt",
                render_kwargs={"focus_instructions": request.guide if request.guide else None},
            )
            if not raw_outline or not raw_outline.strip():
                raise ValueError("Failed to generate monologue outline: empty result")
        except Exception as e:
            error_msg = f"Failed to generate monologue outline: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        logger.info("Task %s: Generating monologue transcript", task_id)
        await self._update_status(task_id, "Generating monologue transcript", progress=0.5)
        try:
            transcript_prompt = self._render_template(
                "transcript_prompt",
                raw_outline=raw_outline,
                documents=request.pdf_metadata,
                focus=request.guide if request.guide else "key areas",
                speaker_1_name=request.speaker_1_name,
            )
            transcript: AIMessage = await self._query_llm(
                [{"role": "user", "content": transcript_prompt}],
                "create_monologue",
            )

            if not transcript or not transcript.content or not transcript.content.strip():
                raise ValueError("Failed to generate monologue transcript: empty result")

            self.prompt_tracker.track(
                "create_monologue",
                transcript_prompt,
                self.llm.model,
                transcript.content,
            )
        except Exception as e:
            error_msg = f"Failed to generate monologue transcript: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        logger.info("Task %s: Finalizing monologue conversation JSON", task_id)
        await self._update_status(task_id, "Finalizing monologue conversation", progress=0.8)
        try:
            final_json = await self._finalize_conversation_json(
                dialogue=transcript.content,
                template_name="dialogue_prompt",
                schema=Conversation.model_json_schema(),
                speaker_1_name=request.speaker_1_name,
                speaker_2_name=None,
            )

            if not final_json:
                raise ValueError("Failed to finalize monologue conversation JSON: empty result")
        except Exception as e:
            error_msg = f"Failed to finalize monologue conversation JSON: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        if "dialogues" in final_json:
            for entry in final_json["dialogues"]:
                if "text" in entry:
                    entry["text"] = self._unescape_unicode_string(entry["text"])

        return Conversation.model_validate(final_json)

    async def run_podcast(self, *, pdfs: Sequence[PdfMetadata], request: Any, task_id: str) -> Conversation:
        """Generate a podcast conversation from PDF documents.

        Args:
            pdfs (Sequence[PdfMetadata]): Sequence of PDF metadata objects to process.
            request (Any): Request object containing speaker names, duration, guide, and PDF metadata.
            task_id (str): Task identifier for logging and tracking.

        Returns:
            Conversation: Generated podcast conversation model.

        Raises:
            ValueError: If speaker_2_name is not provided.
        """
        logger.info("Task %s: Starting podcast generation", task_id)
        await self._update_status(task_id, "Starting podcast generation")
        if not request.speaker_2_name:
            raise ValueError("speaker_2_name is required for podcast flow")

        logger.info("Task %s: Summarizing %d PDF(s)", task_id, len(pdfs))
        await self._update_status(task_id, f"Summarizing {len(pdfs)} PDF document(s)", progress=0.05)
        summarized = await self._summarize_pdfs(
            pdfs,
            template_name="summary_prompt",
        )

        documents_xml = [
            f"""
            <document>
            <type>{"Target Document" if pdf.type == "target" else "Context Document"}</type>
            <path>{pdf.filename}</path>
            <summary>
            {pdf.summary}
            </summary>
            </document>"""
            for pdf in summarized
        ]

        logger.info("Task %s: Generating podcast outline", task_id)
        await self._update_status(task_id, "Generating podcast outline", progress=0.15)
        try:
            raw_outline = await self._generate_raw_outline(
                documents="\n\n".join(documents_xml),
                template_name="multi_pdf_outline_prompt",
                render_kwargs={
                    "total_duration": request.duration,
                    "focus_instructions": request.guide if request.guide else None,
                },
            )
            if not raw_outline or not raw_outline.strip():
                raise ValueError("Failed to generate podcast outline: empty result")
        except Exception as e:
            error_msg = f"Failed to generate podcast outline: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        logger.info("Task %s: Structuring podcast outline", task_id)
        await self._update_status(task_id, "Structuring podcast outline", progress=0.2)
        try:
            outline_schema = PodcastOutline.model_json_schema()
            outline_schema["$defs"]["PodcastSegment"]["properties"]["references"]["items"] = {
                "type": "string",
                "enum": [pdf.filename for pdf in request.pdf_metadata],
            }
            structured_outline = await self._generate_structured_outline(
                raw_outline=raw_outline,
                template_name="multi_pdf_structured_outline_prompt",
                schema=outline_schema,
                valid_filenames=[pdf.filename for pdf in request.pdf_metadata],
            )
            if not structured_outline:
                raise ValueError("Failed to structure podcast outline: empty result")

            outline_model = PodcastOutline.model_validate(structured_outline)
            if not outline_model.segments:
                raise ValueError("Podcast outline has no segments")

            logger.info("Task %s: Generated outline with %d segment(s)", task_id, len(outline_model.segments))
        except Exception as e:
            error_msg = f"Failed to structure podcast outline: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        logger.info("Task %s: Generating segment content", task_id)
        total_segments = len(outline_model.segments)
        await self._update_status(task_id, f"Generating content for {total_segments} segment(s)", progress=0.25)
        segments: dict[str, str] = {}
        for idx, segment in enumerate(outline_model.segments):
            try:
                text_content: str | None = None
                if segment.references:
                    refs = []
                    for ref in segment.references:
                        pdf = next((pdf for pdf in request.pdf_metadata if pdf.filename == ref), None)
                        if pdf:
                            refs.append(pdf.markdown)
                    if refs:
                        text_content = "\n\n".join(refs)

                angles = "\n".join([topic.title for topic in segment.topics])
                segment_result = await self._generate_segment_content(
                    segment_idx=idx,
                    duration=segment.duration,
                    topic=segment.section,
                    angles=angles,
                    template_with_refs="prompt_with_references",
                    template_no_refs="no_references_prompt",
                    text_content=text_content,
                )

                # Validate that segment was generated successfully
                segment_key = f"segment_transcript_{idx}"
                if segment_key not in segment_result or not segment_result[segment_key]:
                    raise ValueError(f"Failed to generate content for segment {idx}: empty result")

                segments.update(segment_result)
                segment_progress = 0.25 + (idx + 1) / total_segments * 0.35
                await self._update_status(
                    task_id, f"Generated segment {idx + 1}/{total_segments}", progress=segment_progress
                )
                logger.info(
                    "Task %s: Generated content for segment %d/%d", task_id, idx + 1, len(outline_model.segments)
                )
            except Exception as e:
                error_msg = f"Failed to generate segment {idx} (section: {segment.section}): {str(e)}"
                logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e

        if not segments:
            raise RuntimeError(f"Task {task_id}: No segments were generated successfully")

        logger.info("Task %s: Generated content for %d segment(s)", task_id, len(segments))

        logger.info("Task %s: Converting segments to dialogue", task_id)
        await self._update_status(task_id, f"Converting {total_segments} segment(s) to dialogue", progress=0.6)
        segment_dialogues = []
        for idx, segment in enumerate(outline_model.segments):
            seg_text = segments.get(f"segment_transcript_{idx}")

            if not seg_text:
                error_msg = f"Segment {idx} (section: {segment.section}) has no transcript content"
                logger.error("Task %s: %s", task_id, error_msg)
                raise RuntimeError(f"Task {task_id}: {error_msg}")

            try:
                descriptions = self._format_topics(segment.topics)
                dialogue = await self._convert_segment_to_dialogue(
                    segment_idx=idx,
                    segment_text=seg_text,
                    template_name="transcript_to_dialogue_prompt",
                    speaker_1_name=request.speaker_1_name,
                    speaker_2_name=request.speaker_2_name,
                    duration=segment.duration,
                    descriptions=descriptions,
                )

                # Validate that dialogue was generated successfully
                if not dialogue or not dialogue.strip():
                    raise ValueError(f"Failed to convert segment {idx} to dialogue: empty result")

                segment_dialogues.append({"section": segment.section, "dialogue": dialogue})
                dialogue_progress = 0.6 + (len(segment_dialogues) / total_segments) * 0.2
                await self._update_status(
                    task_id,
                    f"Converted {len(segment_dialogues)}/{total_segments} segment(s) to dialogue",
                    progress=dialogue_progress,
                )
                logger.info(
                    "Task %s: Converted segment %d/%d to dialogue",
                    task_id,
                    len(segment_dialogues),
                    len(outline_model.segments),
                )
            except Exception as e:
                error_msg = f"Failed to convert segment {idx} (section: {segment.section}) to dialogue: {str(e)}"
                logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
                raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        if not segment_dialogues:
            raise RuntimeError(f"Task {task_id}: No dialogues were generated successfully")

        logger.info("Task %s: Converted %d segment(s) to dialogue", task_id, len(segment_dialogues))

        logger.info("Task %s: Combining dialogues", task_id)
        await self._update_status(task_id, "Combining dialogues", progress=0.85)
        try:
            combined_dialogue = await self._combine_dialogues(
                segment_dialogues=segment_dialogues,
                outline=outline_model,
                template_name="combine_dialogues_prompt",
                task_id=task_id,
            )

            if not combined_dialogue or not combined_dialogue.strip():
                raise ValueError("Failed to combine dialogues: empty result")
        except Exception as e:
            error_msg = f"Failed to combine dialogues: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        logger.info("Task %s: Finalizing podcast conversation JSON", task_id)
        await self._update_status(task_id, "Finalizing podcast conversation", progress=0.9)
        try:
            final_schema = Conversation.model_json_schema()
            final_json = await self._finalize_conversation_json(
                dialogue=combined_dialogue,
                template_name="dialogue_prompt",
                schema=final_schema,
                speaker_1_name=request.speaker_1_name,
                speaker_2_name=request.speaker_2_name,
            )

            if not final_json:
                raise ValueError("Failed to finalize conversation JSON: empty result")
        except Exception as e:
            error_msg = f"Failed to finalize conversation JSON: {str(e)}"
            logger.error("Task %s: %s", task_id, error_msg, exc_info=True)
            raise RuntimeError(f"Task {task_id}: {error_msg}") from e

        if "dialogues" in final_json:
            for entry in final_json["dialogues"]:
                if "text" in entry:
                    entry["text"] = self._unescape_unicode_string(entry["text"])

        return Conversation.model_validate(final_json)

    def _render_template(self, template_name: str, **kwargs: Any) -> str:
        """Render a Jinja2 template with provided keyword arguments.

        Args:
            template_name (str): Name of the template to render.
            **kwargs (Any): Keyword arguments to pass to the template.

        Returns:
            str: Rendered template string.
        """
        return self.templates[template_name].render(**kwargs)

    async def _summarize_pdfs(
        self, pdfs: Sequence[Any], *, template_name: str, prompt_prefix: str = "summarize"
    ) -> list[Any]:
        """Summarize multiple PDF documents using LLM.

        Args:
            pdfs (Sequence[Any]): Sequence of PDF objects with markdown content.
            template_name (str): Name of the prompt template to use for summarization.
            prompt_prefix (str): Prefix for prompt tracking step names. Defaults to "summarize".

        Returns:
            list[Any]: List of PDF objects with updated summary fields.
        """

        async def _summ(pdf: Any) -> Any:
            prompt = self._render_template(template_name, text=pdf.markdown)
            resp: AIMessage = await self._query_llm(
                [{"role": "user", "content": prompt}],
                f"{prompt_prefix}_{pdf.filename}",
            )
            self.prompt_tracker.track(
                f"{prompt_prefix}_{pdf.filename}",
                prompt,
                self.llm.model,
            )
            pdf.summary = resp.content
            self.prompt_tracker.update_result(f"{prompt_prefix}_{pdf.filename}", pdf.summary)
            return pdf

        return await asyncio.gather(*[_summ(pdf) for pdf in pdfs])

    async def _generate_raw_outline(
        self, *, documents: str, template_name: str, render_kwargs: dict[str, Any] | None = None
    ) -> str:
        """Generate a raw outline from documents using LLM.

        Args:
            documents (str): Concatenated document summaries or content.
            template_name (str): Name of the prompt template to use.
            render_kwargs (dict[str, Any] | None): Optional additional keyword arguments for template rendering.
                Defaults to None.

        Returns:
            str: Raw outline text generated by the LLM.
        """
        prompt = self._render_template(template_name, documents=documents, **(render_kwargs or {}))
        outline_msg: AIMessage = await self._query_llm(
            [{"role": "user", "content": prompt}],
            "raw_outline",
        )
        self.prompt_tracker.track(
            "raw_outline",
            prompt,
            self.llm.model,
            outline_msg.content,
        )
        return outline_msg.content

    async def _generate_structured_outline(
        self,
        *,
        raw_outline: str,
        template_name: str,
        schema: dict[str, Any],
        valid_filenames: Iterable[str],
        render_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert a raw outline into a structured JSON outline matching the schema.

        Args:
            raw_outline (str): Raw outline text from previous step.
            template_name (str): Name of the prompt template to use.
            schema (dict[str, Any]): JSON schema to validate the structured output.
            valid_filenames (Iterable[str]): List of valid PDF filenames for reference validation.
            render_kwargs (dict[str, Any] | None): Optional additional keyword arguments for template rendering.
                Defaults to None.

        Returns:
            dict[str, Any]: Structured outline dictionary matching the provided schema.
        """
        prompt = self._render_template(
            template_name,
            outline=raw_outline,
            schema=json.dumps(schema, indent=2),
            valid_filenames=list(valid_filenames),
            **(render_kwargs or {}),
        )
        outline: dict[str, Any] = await self._query_llm(
            [{"role": "user", "content": prompt}],
            "outline",
            json_schema=schema,
        )
        self.prompt_tracker.track("outline", prompt, self.llm.model, json.dumps(outline))
        return outline

    async def _generate_segment_content(
        self,
        segment_idx: int,
        duration: int,
        topic: str,
        angles: str,
        template_with_refs: str,
        template_no_refs: str,
        text_content: str | None = None,
    ) -> dict[str, str]:
        """Generate content for a single podcast segment.

        Args:
            segment_idx (int): Index of the segment being generated.
            duration (int): Duration of the segment in minutes.
            topic (str): Topic or section name for the segment.
            angles (str): Discussion angles or subtopics for the segment.
            template_with_refs (str): Template name to use when text_content is provided.
            template_no_refs (str): Template name to use when text_content is None.
            text_content (str | None): Optional reference text content from PDFs. Defaults to None.

        Returns:
            dict[str, str]: Dictionary with key "segment_transcript_{segment_idx}" and transcript content as value.
        """
        if text_content:
            prompt = self._render_template(
                template_with_refs,
                topic=topic,
                angles=angles,
                duration=duration,
                text=text_content,
            )
        else:
            prompt = self._render_template(
                template_no_refs,
                topic=topic,
                angles=angles,
                duration=duration,
            )
        response: AIMessage = await self._query_llm(
            [{"role": "user", "content": prompt}],
            f"segment_transcript_{segment_idx}",
        )
        self.prompt_tracker.track(
            f"segment_transcript_{segment_idx}",
            prompt,
            self.llm.model,
            response.content,
        )
        return {f"segment_transcript_{segment_idx}": response.content}

    async def _convert_segment_to_dialogue(
        self,
        segment_idx: int,
        segment_text: str,
        template_name: str,
        speaker_1_name: str,
        speaker_2_name: str,
        duration: int,
        descriptions: str,
    ) -> str:
        """Convert a segment transcript into a dialogue format between two speakers.

        Args:
            segment_idx (int): Index of the segment being converted.
            segment_text (str): Transcript text for the segment.
            template_name (str): Name of the prompt template to use.
            speaker_1_name (str): Name of the first speaker.
            speaker_2_name (str): Name of the second speaker.
            duration (int): Duration of the segment in minutes.
            descriptions (str): Formatted topic descriptions for the segment.

        Returns:
            str: Dialogue text with speaker interactions.
        """
        prompt = self._render_template(
            template_name,
            segment_text=segment_text,
            speaker_1_name=speaker_1_name,
            speaker_2_name=speaker_2_name,
            duration=duration,
            descriptions=descriptions,
        )
        dialogue_msg: AIMessage = await self._query_llm(
            [{"role": "user", "content": prompt}],
            f"segment_dialogue_{segment_idx}",
        )
        self.prompt_tracker.track(
            f"segment_dialogue_{segment_idx}",
            prompt,
            self.llm.model,
            dialogue_msg.content,
        )
        return dialogue_msg.content

    async def _combine_dialogues(
        self,
        *,
        segment_dialogues: list[dict[str, str]],
        outline: Any,
        template_name: str,
        task_id: str,
    ) -> str:
        """Iteratively combine multiple segment dialogues into a single cohesive dialogue.

        Args:
            segment_dialogues (list[dict[str, str]]): List of dictionaries with "section" and "dialogue" keys.
            outline (Any): PodcastOutline object.
            template_name (str): Name of the prompt template to use.
            task_id (str): Task identifier for status updates.

        Returns:
            str: Combined dialogue text.
        """
        if not segment_dialogues:
            raise ValueError("No segment dialogues to combine")

        # Start with the first segment's dialogue
        current_dialogue = segment_dialogues[0]["dialogue"]
        self.prompt_tracker.update_result("segment_dialogue_0", current_dialogue)

        # Iteratively combine with subsequent segments
        for idx in range(1, len(segment_dialogues)):
            await self._update_status(
                task_id,
                f"Combining segment {idx + 1}/{len(segment_dialogues)} with existing dialogue",
                progress=0.85 + (idx / len(segment_dialogues)) * 0.05,
            )

            next_section = segment_dialogues[idx]["dialogue"]
            current_section = segment_dialogues[idx]["section"]
            self.prompt_tracker.update_result(f"segment_dialogue_{idx}", next_section)

            prompt = self._render_template(
                template_name,
                outline=outline.model_dump_json(),
                dialogue_transcript=current_dialogue,
                next_section=next_section,
                current_section=current_section,
            )

            combined: AIMessage = await self._query_llm(
                [{"role": "user", "content": prompt}],
                f"combine_dialogues_{idx}",
            )

            self.prompt_tracker.track(
                f"combine_dialogues_{idx}",
                prompt,
                self.llm.model,
                combined.content,
            )

            current_dialogue = combined.content

        return current_dialogue

    async def _finalize_conversation_json(
        self,
        *,
        dialogue: str,
        template_name: str,
        schema: dict[str, Any],
        speaker_1_name: str,
        speaker_2_name: str | None,
    ) -> dict[str, Any]:
        """Convert dialogue text into structured JSON conversation format.

        Args:
            dialogue (str): Dialogue text to convert.
            template_name (str): Name of the prompt template to use.
            schema (dict[str, Any]): JSON schema to validate the output.
            speaker_1_name (str): Name of the first speaker.
            speaker_2_name (str | None): Name of the second speaker, or None for monologue.

        Returns:
            dict[str, Any]: Structured conversation dictionary matching the schema.
        """
        # For monologue template, use 'text' parameter; for podcast, use 'dialogue'
        render_kwargs = {
            "dialogue": dialogue,
            "text": dialogue,  # Support both 'text' (monologue) and 'dialogue' (podcast) template variables
            "schema": json.dumps(schema, indent=2),
            "speaker_1_name": speaker_1_name,
            "speaker_2_name": speaker_2_name,
        }
        prompt = self._render_template(template_name, **render_kwargs)
        final_json: dict[str, Any] = await self._query_llm(
            [{"role": "user", "content": prompt}],
            "final_json",
            json_schema=schema,
        )
        self.prompt_tracker.track(
            "final_json",
            prompt,
            self.llm.model,
            json.dumps(final_json),
        )
        return final_json

    async def _query_llm(
        self,
        messages: list[dict[str, str]],
        query_name: str,
        json_schema: dict | None = None,
        retries: int = 5,
    ) -> AIMessage | dict[str, object]:
        """Query LLM with optional structured output and retries.

        Args:
            messages (list[dict[str, str]]): List of message dictionaries
            query_name (str): Logical name/tag for logging and error context
            json_schema (dict | None): Schema for structured output
            retries (int): Number of retry attempts

        Returns:
            AIMessage | dict[str, object]: Model response

        Raises:
            Exception: If query fails after retries
        """
        try:
            llm = self.llm

            if json_schema:
                llm = llm.with_structured_output(json_schema)

            llm = llm.with_retry(stop_after_attempt=retries, wait_exponential_jitter=True)
            return await llm.ainvoke(messages)

        except Exception as exc:
            logger.error("Async LLM query '%s' failed: %s", query_name, exc)
            raise Exception(f"Async LLM query '{query_name}' failed after {retries} attempts") from exc

    @staticmethod
    def _unescape_unicode_string(s: str) -> str:
        """Unescape Unicode escape sequences in a string.

        Args:
            s (str): String potentially containing Unicode escape sequences.

        Returns:
            str: String with unescaped Unicode characters, or original string if decoding fails.
        """
        try:
            return s.encode("utf-8").decode("unicode_escape")
        except Exception:
            return s

    @staticmethod
    def _format_topics(topics: Sequence[Any]) -> str:
        """Format topic objects into a structured string representation.

        Args:
            topics (Sequence[Any]): Sequence of topic objects with title and points attributes.

        Returns:
            str: Formatted string with topic titles and bullet points.
        """
        descriptions = []

        for topic in topics:
            bullet_points = "\n".join([f"- {point.description}" for point in topic.points])
            descriptions.append(f"{topic.title}:\n{bullet_points}")

        return "\n\n".join(descriptions)
