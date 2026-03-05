# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Core utilities
import argparse  # CLI argument parsing
import ast  # Python source analysis
import json  # JSON data handling
import logging  # Structured logging
import os  # System operations
from pathlib import Path

# Type system & utilities
from typing import Any
from urllib.parse import urlparse  # URL manipulation

# Web frameworks
import gradio as gr  # Interactive UI
import nltk
import requests  # HTTP requests
import uvicorn  # Production server
from fastapi import FastAPI  # REST API

# Document processing
from langchain_community.document_loaders import UnstructuredURLLoader  # Web scraping

# Setup application logging
log = logging.getLogger("summarizer_ui")
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class ContentProcessor:
    """Processes various content types for AI summarization."""

    def __init__(self):
        self.DOC_EXTS = {".pdf", ".docx"}
        self.AUDIO_FORMATS = {".mp3", ".wav"}
        self.VIDEO_FORMATS = {".mp4"}
        self.API_HEADERS = {"Content-Type": "application/json"}
        self.API_TARGET = os.getenv("SUMMARY_SERVICE_URL", "http://localhost:8888/v1/summarize")

    def check_url_format(self, link: str) -> bool:
        parsed = urlparse(link)
        return all([parsed.scheme, parsed.netloc])

    def scrape_webpage(self, link: str) -> str:
        log.info("Processing webpage: %s", link)
        if not self.check_url_format(link):
            return f"Malformed URL: {link}"

        no_proxy_val = os.environ.get("no_proxy", "")
        os.environ["no_proxy"] = f"{no_proxy_val},{link}".rstrip(",")

        try:
            content_loader = UnstructuredURLLoader(urls=[link])
            docs = content_loader.load()
            return docs[0].page_content if docs else ""
        except Exception as err:
            msg = f"Webpage load failed: {err}"
            log.error(msg)
            return msg

    def parse_api_result(self, api_response):
        if api_response.status_code != 200:
            return f"API Error {api_response.status_code}: {api_response.text}"

        content = api_response.text
        try:
            parsed = json.loads(content)
            if parsed.get("choices"):
                first_choice = parsed["choices"][0]
                msg = first_choice.get("message", {}).get("content")
                return msg.strip() if msg else first_choice.get("text", "").strip()
            for field in ("summary", "text", "output_text"):
                if field in parsed:
                    return str(parsed[field]).strip()
        except json.JSONDecodeError as decode_err:
            log.warning("Failed to decode API JSON response: %s", decode_err)

        if "LLMChain/final_output" in content:
            log_lines = content.split("\n\n")
            final_logs = [line.partition("data: ")[2] for line in log_lines if "LLMChain/final_output" in line]
            if final_logs:
                data = ast.literal_eval(final_logs[-1])["ops"]
                final_vals = [op["value"] for op in data if op["path"].endswith("final_output")]
                return final_vals[-1]["text"] if final_vals else ""

        SSE_CLEANUP_PATTERNS = {
            "data_prefix": "data: b' ",
            "newline_data": "'\n\ndata: ",
            "done_marker": "[DONE]",
            "empty_data": "\n\ndata:",
            "quote_newline": "'\n",
            "escaped_quote": r"\"",
        }

        for pattern_name, replacement in SSE_CLEANUP_PATTERNS.items():
            content = content.replace(pattern_name, replacement)
        return content.strip()

    def submit_content(self, input_data: Any, media_kind: str = "text") -> str:
        log.info("Submitting to %s", self.API_TARGET)

        if hasattr(input_data, "name") and getattr(input_data, "name", None):
            return self._handle_gradio_file(input_data, media_kind)

        request_data = {
            "max_tokens": 2048,
            "type": media_kind,
            "messages": '[{"role": "user", "content": "' + json.dumps(str(input_data)) + '"}]',
        }

        try:
            result = requests.post(
                str(self.API_TARGET),
                headers=self.API_HEADERS,
                json=request_data,
                proxies=self.proxy_settings(),
                timeout=300,
            )
            return self.parse_api_result(result)
        except requests.RequestException as api_err:
            log.error("API call failed: %s", api_err)
            return f"API Error: {api_err}"

    def _handle_gradio_file(self, gradio_file, media_kind: str) -> str:
        try:
            file_path = Path(gradio_file.name)
            file_name = gradio_file.name.split("/")[-1]  # Имя без пути
            file_ext = Path(file_name).suffix

            content_type = {
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain",
            }.get(file_ext, "application/octet-stream")

            with open(file_path, "rb") as f:
                files = {"files": (file_name, f, content_type)}
                data = {"type": media_kind, "messages": '[{"role":"user","content":"summarize"}]', "max_tokens": 2048}

                result = requests.post(str(self.API_TARGET), files=files, data=data, timeout=300)
            return self.parse_api_result(result)

        except Exception as e:
            log.error(f"File handling failed: {e}")
            return f"File error: {e}"

    def proxy_settings(self):
        return {
            "http": os.getenv("http_proxy"),
            "https": os.getenv("https_proxy"),
        }

    def create_upload_section(self, section_title: str, file_exts: set, media_kind: str = "text"):
        with gr.Row():
            file_selector = gr.File(
                label=section_title,
                file_types=list(file_exts),
                file_count="single",
            )
            preview_area = gr.Textbox(
                label="Processing Result",
                lines=12,
                placeholder="Upload file to see results...",
            )

        def _handle_file(f):
            if f is None:
                return ""
            return self.submit_content(f, media_kind)

        file_selector.change(_handle_file, file_selector, preview_area)

    def create_app(self):
        with gr.Blocks(title="AI Content Processor", theme=gr.themes.Soft()) as app_demo:
            gr.Markdown("# Document Summarization")

            with gr.Accordion("How to use this app", open=False):
                gr.Markdown(
                    """
                    1. Select an input tab (Text, Documents, Audio, or Video)
                    2. Paste text or upload a file
                    3. Click **Generate Summary** (for text input)
                    4. View the generated summary on the right
                    """
                )

            input_tabs = gr.Tabs()
            with input_tabs:
                text_tab = gr.TabItem("Text Input")
                with text_tab:
                    main_layout = gr.Row(equal_height=True)
                    with main_layout:
                        input_section = gr.Column()
                        with input_section:
                            content_field = gr.TextArea(
                                label="Enter text to summarize",
                                placeholder="Paste your document, article, or any text content here...",
                            )
                            process_btn = gr.Button("Generate Summary", variant="primary", size="lg")

                        output_section = gr.Column()
                        with output_section:
                            output_panel = gr.Markdown(
                                label="Summary", value="**Upload or paste content above to get instant summary...**"
                            )
                process_btn.click(self.submit_content, content_field, output_panel)

                with gr.TabItem("Documents"):
                    self.create_upload_section("PDF, DOCX", self.DOC_EXTS, "text")

                with gr.TabItem("Audio"):
                    self.create_upload_section("Audio Files", self.AUDIO_FORMATS, "audio")

                with gr.TabItem("Video"):
                    self.create_upload_section("Video Files", self.VIDEO_FORMATS, "video")

            process_btn.click(fn=self.submit_content, inputs=content_field, outputs=output_panel)

        return app_demo


def main():
    nltk.download("punkt_tab", quiet=True)
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)

    api_app = FastAPI(title="Document Summarization")
    ui_component = ContentProcessor().create_app()

    ui_component.queue(max_size=10)

    api_app = gr.mount_gradio_app(api_app, ui_component, path="/")

    cli_parser = argparse.ArgumentParser(
        description="AI Content Processor UI Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    cli_parser.add_argument("--host", default="0.0.0.0", help="Server bind address")
    cli_parser.add_argument("--port", type=int, default=5173, help="Server port number")
    server_config = cli_parser.parse_args()

    log.info("Starting UI server | host=%s port=%d queue_size=%d", server_config.host, server_config.port, 10)

    uvicorn.run(api_app, host=server_config.host, port=server_config.port, log_level="info")


if __name__ == "__main__":
    main()
