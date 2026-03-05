# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Celery tasks for PDF conversion using docling."""


import gc
import logging
from pathlib import Path

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from infrastructure.celery_client import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="pdf.convert", max_retries=3)
def convert_pdfs(task_id: str, payload: list[dict], storage_path: str) -> list[dict]:
    """Convert PDFs to markdown using docling.

    Args:
        task_id (str): Task identifier (for logging).
        payload (list[dict]): List of PDF files with keys:
            - filename (str): Original filename
            - file_path (str): Absolute path to PDF file in shared storage
            - type (str): Document type ("target" or "context")
        storage_path (str): Base storage path (for validation).

    Returns:
        list[dict]: Conversion results with keys:
            - filename (str): Original filename
            - content (str): Markdown content
            - status (str): "success" or "failed"
            - error (str | None): Error message if failed
    """
    logger.info("Starting PDF conversion for task %s, %d files", task_id, len(payload))
    results: list[dict] = []
    converter = None

    try:
        pipeline_options = PdfPipelineOptions(do_ocr=False)
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options, backend=PyPdfiumDocumentBackend)
            }
        )

        for item in payload:
            filename = item.get("filename", "document.pdf")
            file_path_str = item.get("file_path", "")
            doc_type = item.get("type", "target")
            result = None
            markdown_content = None

            try:
                file_path = Path(file_path_str)

                # Security check: ensure file is within storage path
                storage_base = Path(storage_path).resolve()
                if not file_path.resolve().is_relative_to(storage_base):
                    raise ValueError(f"File path {file_path} is outside storage directory {storage_base}")

                if not file_path.exists():
                    raise FileNotFoundError(f"PDF file not found: {file_path}")

                # Convert PDF to markdown using docling
                result = converter.convert(file_path)
                # Extract markdown from the result
                markdown_content = result.document.export_to_markdown()

                results.append(
                    {
                        "filename": filename,
                        "content": markdown_content,
                        "status": "success",
                        "error": None,
                    }
                )
                logger.info("Successfully converted %s (%s)", filename, doc_type)

            except Exception as exc:
                error_msg = str(exc)
                logger.error("Failed to convert %s: %s", filename, error_msg, exc_info=True)
                results.append(
                    {
                        "filename": filename,
                        "content": "",
                        "status": "failed",
                        "error": error_msg,
                    }
                )
            finally:
                # Explicitly clean up large objects to free memory
                if result is not None:
                    del result

                if markdown_content is not None:
                    del markdown_content

    finally:
        # Clean up converter to free any cached models/resources
        if converter is not None:
            del converter
        # Force garbage collection to ensure memory is freed
        gc.collect()

    successful = sum(1 for r in results if r["status"] == "success")
    logger.info("PDF conversion completed for task %s: %d/%d successful", task_id, successful, len(results))
    return results
