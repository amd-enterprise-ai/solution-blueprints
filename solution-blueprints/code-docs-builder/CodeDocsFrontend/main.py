# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Tuple

import gradio as gr
from apiclient import ApiClient
from werkzeug.utils import secure_filename

# Mermaid diagram style fix (to display light text)
css = """
        .mermaid foreignObject p {
            color: #18181B !important;
        }
        """

# Configure API client
client = ApiClient(base_url=os.getenv("BACKEND_BASE_URL"), timeout=120)


def _ui_action_clone_repository(repo_url: str) -> Tuple[str, str]:
    """
    Wrapper for the UI layer that calls the client clone method.

    Args:
        repo_url: Git repository URL from the UI.

    Returns:
        Tuple[str, str]: (repo_id, status_message) for UI components.
    """
    repo_id, status = client.clone_repository(repo_url)
    return repo_id or "", f"### Status: {status}"


def _parse_progress(status: str) -> float:
    """Map a backend status string to a 0–1 progress fraction."""
    if "Documentation is ready" in status:
        return 1.0
    m = re.search(r"section:\s*(\d+)/(\d+)", status)
    if m:
        n, total = int(m.group(1)), int(m.group(2))
        return 0.5 + (n / total) * 0.45  # 50–95 % range for writing phase
    if "Step 2/2" in status:
        return 0.5
    if "Step 1/2" in status:
        return 0.1
    return 0.03  # "Waiting…" / unknown


def _ui_action_start_generation(repo_id: str, progress=gr.Progress()):
    """
    Start or resume documentation generation, polling status every 5 seconds.
    If generation is already running (model loading or active), skips the POST
    and resumes polling directly — safe to call multiple times.
    """
    button_disabled = gr.update(interactive=False)
    button_enabled = gr.update(interactive=True)

    # 0) Pre-check: is generation already running?
    current_status = client.get_documentation_status(repo_id)

    if current_status == "Documentation is ready":
        progress(1.0)
        yield f"### Status: {current_status}", button_enabled
        return

    already_running = (
        current_status is not None
        and not current_status.startswith("Error")
        and not current_status.startswith("Please provide")
        and current_status != "Failed"
    )

    if already_running:
        progress(_parse_progress(current_status))
        yield f"### Status: {current_status}", button_disabled
    else:
        # 1) Start new generation
        initial_status = client.start_generation(repo_id)
        if initial_status.startswith("Error") or "Please provide" in initial_status:
            yield f"### Status: {initial_status}", button_disabled
            return
        progress(_parse_progress(initial_status))
        yield f"### Status: {initial_status}", button_disabled

    # 2) Poll until terminal state
    while True:
        time.sleep(5)
        status = client.get_documentation_status(repo_id)

        if status is None:
            yield "### Status: Error occurred. Try again later.", button_disabled
            return

        display_status = status

        progress(_parse_progress(status))

        if status == "Documentation is ready":
            yield f"### Status: {status}", button_enabled
            return

        if status == "Failed":
            yield f"### Status: {status}. Try again later.", button_disabled
            return

        yield f"### Status: {display_status}", button_disabled


def _ui_action_fetch_documentation(repo_id: str):
    """
    Wrapper for the UI layer that fetches documentation and prepares
    a temporary file for download plus Markdown preview.

    Args:
        repo_id: Repository ID from the UI.

    Returns:
        (file_path | None, markdown_text, status_message)
    """
    filename, markdown_text, status = client.fetch_documentation(repo_id)

    if filename is None or not markdown_text:
        return None, "", f"### Status: {status}"

    tmp_dir = tempfile.mkdtemp()
    safe_filepath = secure_filename(filename)
    file_path = Path(tmp_dir) / safe_filepath
    file_path.write_text(markdown_text, encoding="utf-8")

    return str(file_path), markdown_text, f"### Status: {status}"


def _toggle_clone_button(repo_url: str) -> gr.Button:
    """
    Enable or disable the Clone button based on repo_url value.

    Args:
        repo_url: Current value of the Git URL input.

    Returns:
        gr.Button: Updated button component configuration.
    """
    return gr.update(interactive=bool(repo_url.strip()))


def _toggle_buttons_by_repo_id(repo_id: str) -> Tuple[gr.Button, gr.Button]:
    """
    Enable or disable Generate and Show Documentation buttons
    based on repo_id value.

    Args:
        repo_id: Current value of the repository ID input.

    Returns:
        Tuple[gr.Button, gr.Button]: Updated button configs.
    """
    is_enabled = bool(repo_id.strip())
    return gr.update(interactive=is_enabled), gr.update(interactive=is_enabled)


with gr.Blocks() as frontend:
    # --- UI Definition ---
    gr.Markdown("# Code Docs Builder")
    gr.Markdown("*Analyzes your GitHub repository and generates structured documentation using AI agents.*")
    status_output = gr.Markdown(value="### Status: Ready to work")

    gr.Markdown("## 1. Clone repository")
    with gr.Row(equal_height=True):
        repo_url_input = gr.Textbox(
            label="Git repository URL",
            placeholder="https://github.com/user/project.git",
            scale=5,
        )
        clone_button = gr.Button("1. Clone", variant="primary", interactive=False, scale=1)

    gr.Markdown("## 2. Generate documentation")
    with gr.Row(equal_height=True):
        repo_id_input = gr.Textbox(label="Repository ID", placeholder="Will be filled after successful clone", scale=5)
        generate_button = gr.Button("2. Generate", variant="primary", interactive=False, scale=1)

    warning_message = gr.Markdown(
        "WARNING: Documentation planning and generation may take **a while** depending on repository size. "
        "Don't forget to check status.",
    )

    gr.Markdown("## 3. Show documentation")
    show_docs_button = gr.Button("3. Show", interactive=False, variant="primary")

    documentation_file = gr.File(
        label="Download documentation (.md)",
        interactive=False,
    )
    documentation_markdown = gr.Markdown(
        label="Documentation text (rendered from Markdown)",
    )

    # --- Wiring ---

    # Enable/disable Clone button based on repo URL
    repo_url_input.change(
        _toggle_clone_button,
        inputs=repo_url_input,
        outputs=clone_button,
    )

    # Clone repository
    clone_button.click(
        fn=_ui_action_clone_repository,
        inputs=repo_url_input,
        outputs=[repo_id_input, status_output],
    )

    # Enable/disable Generate and Show Documentation based on repo_id
    repo_id_input.change(
        _toggle_buttons_by_repo_id,
        inputs=repo_id_input,
        outputs=[generate_button, show_docs_button],
    )

    # Start generation
    generate_button.click(
        fn=_ui_action_start_generation,
        inputs=[repo_id_input],
        outputs=[status_output, show_docs_button],
    )

    # Fetch and display documentation
    show_docs_button.click(
        fn=_ui_action_fetch_documentation,
        inputs=repo_id_input,
        outputs=[documentation_file, documentation_markdown, status_output],
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8092))
    frontend.launch(server_name="0.0.0.0", server_port=port, css=css)
