# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import logging

import gradio as gr
import uvicorn
from backend import KnowledgeBase
from config import GRADIO_PORT, TITLE
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from rag import run_rag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Backend
kb = KnowledgeBase()

# Initialize the Server
app = FastAPI(title=TITLE or "Talk to your documents")


# HEALTH CHECKS
@app.get("/health")
@app.get("//health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# API LOGIC
def process_rag_logic(files, question: str) -> str:
    if files:
        file_paths = [f.name if hasattr(f, "name") else f for f in files]
        kb.build(file_paths)

    final_answer = ""
    full_log = ""
    for chunk in run_rag(question, kb):
        full_log += chunk
        if "**Final Answer:**" in chunk:
            final_answer = chunk.split("**Final Answer:**")[1].strip()

    return final_answer if final_answer else full_log


@app.post("/process")
async def api_process(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "")
        files = data.get("files", [])
        result = await asyncio.to_thread(process_rag_logic, files, question)
        return {"result": result}
    except Exception as exc:
        logger.exception("API Error")
        return JSONResponse(status_code=500, content={"error": "An internal error has occurred."})


# UI LOGIC


def run_rag_ui(files, question):
    """
    Yields 3 values to match the Right Column:
    1. Question Display
    2. Scratchpad (Markdown)
    3. Final Answer (Textbox)
    """
    q_text = question.strip()
    if not q_text:
        yield "", "❌ Please ask a question.", ""
        return

    # 1. Build KB if files exist
    if files:
        yield q_text, "🔄 Processing files...", ""
        file_paths = [f.name for f in files]
        kb.build(file_paths)

    yield q_text, "🔄 Thinking...", ""

    scratchpad = ""
    final = ""

    # 2. Stream chunks
    for chunk in run_rag(q_text, kb):
        if "**Final Answer:**" in chunk:
            parts = chunk.split("**Final Answer:**")
            if parts[0].strip():
                scratchpad += parts[0].strip() + "\n\n"
            final = parts[1].strip()
        else:
            scratchpad += chunk

        yield q_text, scratchpad, final


def clear_all_ui():
    """Clears DB and resets all UI components"""
    kb.clear()
    return None, "", "", "", ""


# UI LAYOUT
with gr.Blocks(title=TITLE) as demo:

    gr.Markdown(f"# {TITLE}")

    with gr.Row(equal_height=False):
        with gr.Column(scale=1):
            gr.Markdown("### User Input & Controls")
            files_input = gr.File(label="Upload Documents", file_count="multiple")
            q_input = gr.Textbox(label="Ask a Question", lines=4, placeholder="Type here...")

            with gr.Row():
                clr_btn = gr.Button("Clear All", variant="secondary")
                sub_btn = gr.Button("Submit", variant="primary")

        with gr.Column(scale=2):
            gr.Markdown("### Reasoning & Final Answer")
            q_display = gr.Textbox(label="Question", interactive=False, lines=2)

            with gr.Accordion("Live Scratchpad", open=True):
                scratchpad_out = gr.Markdown(label="Step-by-Step Process")

            final_out = gr.Textbox(label="Final Answer", lines=8, interactive=False)

    stream_event = sub_btn.click(
        fn=run_rag_ui,
        inputs=[files_input, q_input],
        outputs=[q_display, scratchpad_out, final_out],
        show_progress="full",
    )

    stream_event.then(fn=lambda: "", inputs=None, outputs=[q_input])

    clr_btn.click(fn=clear_all_ui, inputs=None, outputs=[files_input, q_input, q_display, scratchpad_out, final_out])

app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=GRADIO_PORT)
