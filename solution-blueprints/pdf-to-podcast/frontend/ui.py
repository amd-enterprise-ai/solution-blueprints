# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os

import gradio as gr

from .settings import OUTPUT_DIR, UPLOAD_DIR, initialize_directories, setup_logging
from .utils.file_utils import cleanup_files, clear_logs, copy_files_to_upload_dir, ensure_list, read_logs
from .utils.podcast_service import PodcastService

# Setup logging
setup_logging()
# Initialize directories on module import
initialize_directories()

log = logging.getLogger(__name__)


# Gradio Interface
with gr.Blocks(analytics_enabled=False) as demo:
    gr.Markdown("# Blueprint: PDF-to-Podcast")

    with gr.Row():

        with gr.Column(scale=1):
            with gr.Tab("Full End to End Flow"):
                gr.Markdown("### Upload at least one PDF file for a file to target or as context. ")
                with gr.Row():
                    target_file = gr.File(label="Upload target PDF", file_types=[".pdf"])
                    context_files = gr.File(label="Upload context PDF", file_types=[".pdf"], file_count="multiple")
                with gr.Row():
                    settings = gr.CheckboxGroup(
                        ["Monologue Only", "No TTS", "Full audio"],
                        label="Additional Settings",
                        info="Customize your podcast here",
                    )
                gr.Markdown(
                    "- Monologue Only: single speaker, no dialogue.\n"
                    "- No TTS: skip audio generation, transcript only.\n"
                    "- Full audio: generate the full podcast; otherwise audio is limited to 3000 characters.\n"
                    "- Note: if No TTS is selected, audio will not be generated even with Full audio enabled."
                )

                generate_button = gr.Button("Generate Podcast")

        with gr.Column(scale=1):
            gr.Markdown("<br />")
            token_info = gr.Markdown("## Full podcast tokens: —", visible=False)
            output = gr.Textbox(
                label="Outputs", placeholder="Outputs will show here when executing", max_lines=20, lines=20
            )
            audio_file = gr.File(visible=False, interactive=False, label="podcast audio")
            transcript_file = gr.File(visible=False, interactive=False, label="podcast transcript")

    timer = gr.Timer()
    timer.tick(read_logs, None, output)

    def hide_outputs():
        return (
            gr.update(visible=False, value=None),
            gr.update(visible=False, value=None),
            gr.update(visible=False, value=None),
        )

    def generate_podcast(target: str, context: list[str] | None, settings: list[str]):
        # Reset logs for a fresh run
        clear_logs()

        copied_files = []
        try:
            if target is None or len(target) == 0:
                gr.Warning("Target PDF upload not detected. Please upload a target PDF file and try again. ")
                return (
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                )

            target_list: list[str] = ensure_list(target)
            context_list: list[str] = ensure_list(context)

            # Copy files from Gradio temp directory to our upload directory
            copied_targets = copy_files_to_upload_dir(target_list)
            copied_contexts = copy_files_to_upload_dir(context_list)
            copied_files = copied_targets + copied_contexts

            if not copied_targets:
                gr.Warning("Failed to copy target file. Please try again.")
                return (
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                )

            base_url = os.environ["API_SERVICE_URL"]

            podcast_service = PodcastService(base_url=base_url)
            no_tts = "No TTS" in settings
            audio_path, transcript_path, token_count = podcast_service.generate_podcast(
                target_files=copied_targets,
                context_files=copied_contexts,
                settings=settings,
            )

            cleanup_files(copied_files)

            # Handle audio file visibility based on no_tts flag
            audio_update = (
                gr.update(visible=False)
                if (no_tts or audio_path is None)
                else gr.update(value=audio_path, visible=True, label="podcast audio")
            )
            token_value = token_count if token_count is not None else "—"
            token_update = gr.update(value=f"## Full podcast tokens: {token_value}", visible=True)
            return (
                audio_update,
                gr.update(value=transcript_path, visible=True, label="podcast transcript"),
                token_update,
            )
        except Exception as exc:
            log.error("Generation failed: %s", exc)
            cleanup_files(copied_files)
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )

    # First hide any previous outputs on click
    generate_button.click(hide_outputs, outputs=[audio_file, transcript_file, token_info])
    generate_button.click(
        generate_podcast,
        [target_file, context_files, settings],
        [audio_file, transcript_file, token_info],
    )

# Launch Gradio app
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        root_path=os.environ.get("PROXY_PREFIX"),
        allowed_paths=[
            UPLOAD_DIR.absolute().as_posix(),
            OUTPUT_DIR.absolute().as_posix(),
        ],
    )
