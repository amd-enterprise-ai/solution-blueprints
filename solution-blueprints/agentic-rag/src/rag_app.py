# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import html

import gradio as gr
import uvicorn
from backend import ingest_files  # type: ignore[attr-defined]
from config import GRADIO_PORT, MCP_URL, TITLE  # type: ignore[attr-defined]
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from rag_agent import run_rag_agent

from utils import get_service_health, setup_logging  # type: ignore[attr-defined]

# This file is the Gradio UI + FastAPI server.
# It bridges user interactions (file upload, question input) to the RAG agent.

# Initialize centralized logging
logger = setup_logging(__name__)
app = FastAPI(title=TITLE)


# Health endpoint for K8s liveness/readiness probes
# Returns 200 as long as the FastAPI process is alive.
@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


@app.post("/process")
async def api_process(request: Request):
    """Programmatic API access for non-UI requests."""
    try:
        data = await request.json()
        question = data.get("question", "")
        final_answer = ""

        async for chunk in run_rag_agent(question):
            if "**Final Answer:**" in chunk:
                final_answer = chunk.split("**Final Answer:**")[1].strip()

        return {"result": final_answer}
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


async def upload_to_kb(files):
    """Upload files to the Knowledge Base without asking a question."""
    if not files:
        return "<div style='color:red;'>No files selected. Please upload files first.</div>"

    if not get_service_health(MCP_URL):
        return "<div style='padding:10px; background:rgba(255,152,0,0.15); border-left:4px solid #ff9800;'>⚠️ <b>MCP Server not reachable.</b> Please wait and try again.</div>"

    file_paths = [f.name for f in files]
    status_html = ""
    mcp_headers = {"Connection": "keep-alive"}

    try:
        async with sse_client(url=MCP_URL, headers=mcp_headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                async for event in ingest_files(session, file_paths):
                    status_html += event
    except Exception as e:
        logger.error(f"Upload error: {e}")
        status_html += f"<div style='color:red;'>❌ Upload failed: {html.escape(str(e))}</div>"

    return status_html


async def clear_kb():
    """Clear the Knowledge Base."""
    if not get_service_health(MCP_URL):
        return "<div style='padding:10px; background:rgba(255,152,0,0.15); border-left:4px solid #ff9800;'>⚠️ <b>MCP Server not reachable.</b> Please wait and try again.</div>"

    mcp_headers = {"Connection": "keep-alive"}
    try:
        async with sse_client(url=MCP_URL, headers=mcp_headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                await session.call_tool("clear_database", {})
        return "<div style='padding:8px; background:rgba(76,175,80,0.15); border-left:3px solid #4caf50;'>✅ Knowledge Base cleared.</div>"
    except Exception as e:
        logger.error(f"Clear KB error: {e}")
        return f"<div style='color:red;'>❌ Failed to clear: {html.escape(str(e))}</div>"


async def run_rag_ui(question):
    """The main UI bridge for the Agentic RAG generator.
    Files are NOT ingested here — use 'Upload to Knowledge Base' first."""
    q_text = question if question else ""
    q_text = q_text.strip()
    if not q_text:
        yield q_text, "<div style='color:red;'>Please enter a question.</div>", "", ""
        return

    # Pre-flight: check MCP connectivity before starting the agent.
    if not get_service_health(MCP_URL):
        yield q_text, "<div style='padding:10px; background:rgba(255,152,0,0.15); border-left:4px solid #ff9800;'>⚠️ <b>MCP Server not reachable.</b> Please wait a moment and try again.</div>", "", ""
        return

    trace_html = ""
    final_answer = ""

    yield q_text, "🚀 <b>Agent Initializing...</b>", "", ""

    try:
        async for chunk in run_rag_agent(q_text):
            # Check for final answer in the chunk
            if "**Final Answer:**" in chunk:
                parts = chunk.split("**Final Answer:**")
                # Add any trace content before the marker
                if parts[0].strip():
                    trace_html += parts[0].strip()
                # The rest is the answer
                final_answer += parts[1].strip()
            else:
                trace_html += chunk

            # Yield update to UI
            yield q_text, trace_html, final_answer, ""

    except GeneratorExit:
        # User navigated away or pressed Clear during streaming.
        # This is normal; Gradio cancels the generator. Safe to ignore.
        logger.info("UI stream cancelled by client (GeneratorExit)")
    except ConnectionError as e:
        logger.error(f"Connection lost during streaming: {e}")
        error_box = "<div style='padding:10px; background:rgba(244,67,54,0.15); border-left:4px solid #f44336;'>❌ <b>Connection lost.</b> Please refresh the page and try again.</div>"
        yield q_text, trace_html + error_box, final_answer, ""
    except Exception as e:
        logger.error(f"UI Stream Error: {type(e).__name__}: {e}")
        error_box = "<div style='padding:10px; background:rgba(244,67,54,0.15); border-left:4px solid #f44336;'>❌ <b>Error:</b> An unexpected error occurred. Please try again.</div>"
        yield q_text, trace_html + error_box, final_answer, ""


custom_css = """
.trace-box { height: 550px; overflow-y: auto; border: 1px solid rgba(128,128,128,0.3); padding: 10px; }
.final-box textarea { font-size: 1.1em !important; border: 2px solid #4caf50 !important; }
"""

# Clear via client-side JS (runs entirely in the browser)
# No server round-trip needed, so it never fails even if the backend is busy.
# Returns null/empty for each output component to reset the UI.
CLEAR_JS = """
() => {
    return [null, '', '', '', '', ''];
}
"""

with gr.Blocks(title=TITLE, css=custom_css) as demo:
    gr.Markdown(f"# {TITLE}")
    gr.Markdown(
        "Upload your documents and ask questions — this agent retrieves relevant context from your files and generates grounded answers using RAG."
    )

    with gr.Row():
        with gr.Column(scale=1):
            # --- How to use ---
            gr.HTML(
                """
<div style="padding:12px 16px;background:rgba(33,150,243,0.1);border-left:4px solid #2196f3;border-radius:4px;margin-bottom:8px;">
  <b>How to use</b>
  <ol style="margin:6px 0 0 0;padding-left:20px;">
    <li>Upload one or more documents (PDF or TXT).</li>
    <li>Click <b>Upload to Knowledge Base</b> to index them.</li>
    <li>Type a question related to your documents.</li>
    <li>Click <b>Ask Agent</b> to get an answer grounded in the uploaded content.</li>
  </ol>
</div>
"""
            )
            # --- Knowledge Base Management ---
            gr.Markdown("### Knowledge Base")
            file_upload = gr.File(label="Upload Documents", file_count="multiple")
            with gr.Row():
                btn_upload_kb = gr.Button("Upload to Knowledge Base", variant="primary")
                btn_clear_kb = gr.Button("Clear Knowledge Base", variant="stop")
            kb_status = gr.HTML(label="KB Status", value="")

            # --- Question ---
            gr.Markdown("### Ask a Question")
            user_input = gr.Textbox(
                label="Your question", lines=4, placeholder="Ask a question about your uploaded documents..."
            )
            with gr.Row():
                btn_clear = gr.Button("Clear")
                btn_run = gr.Button("Ask Agent", variant="primary")

        with gr.Column(scale=2):
            active_question = gr.Textbox(label="Active Question", interactive=False)
            with gr.Accordion("Agent Reasoning Trace", open=True):
                trace_output = gr.HTML(label="Reasoning Logs", elem_classes=["trace-box"])

            answer_output = gr.Textbox(label="Final Result", lines=10, interactive=False, elem_classes=["final-box"])

    btn_upload_kb.click(
        fn=upload_to_kb,
        inputs=[file_upload],
        outputs=[kb_status],
    )

    btn_clear_kb.click(
        fn=clear_kb,
        inputs=None,
        outputs=[kb_status],
    )

    btn_run.click(
        fn=run_rag_ui,
        inputs=[user_input],
        outputs=[active_question, trace_output, answer_output, user_input],
    )

    btn_clear.click(
        fn=None,
        inputs=None,
        outputs=[file_upload, user_input, active_question, trace_output, answer_output, kb_status],
        js=CLEAR_JS,
    )

# Mount Gradio app inside FastAPI so both share the same port.
# Gradio serves at "/", FastAPI endpoints at "/healthz", "/process", etc.
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=GRADIO_PORT)
