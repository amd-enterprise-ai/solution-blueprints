# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
FastAPI backend for report generation.

Provides REST API endpoints for generating reports using the existing
report generation pipeline.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from rge_client_factory import create_llm_client, create_tavily_client
from rge_config import Config, get_config
from rge_models import ReportRequest, ReportResponse, Section
from rge_report_generator import ReportGenerator
from rge_utils import count_words

# Configure logging for all rge_* modules
# Set up root logger to capture logs from all modules (rge_api, rge_report_generator, etc.)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("rge_api")

# Global state (initialized on startup)
config: Optional[Config] = None
generator: Optional[ReportGenerator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    global config, generator
    try:
        logger.info("Initializing Report Generator API...")

        # Load unified configuration
        config = get_config()

        # Create clients
        llm = create_llm_client(config)
        tavily = create_tavily_client(config)  # May be None if no API key

        # Create generator
        generator = ReportGenerator(llm, tavily, config)

        logger.info("Done - Report Generator API started successfully")
        if tavily is None:
            logger.warning("Tavily: NOT CONFIGURED - report generation will fail")

        yield  # Application runs here

    except Exception as e:
        logger.error("STARTUP FAILED: %s", e, exc_info=True)
        raise


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Report Generator API",
    version="1.0.0",
    description="AI-powered structured report generation with web research",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for liveness probe.
    Returns:
        dict: Service health status
    """
    return {"status": "healthy", "service": "report-generator"}


@app.get("/readiness")
async def readiness_check():
    """
    Readiness check endpoint for Kubernetes readiness probe.
    Returns 200 when service is ready to accept traffic.
    Returns:
        dict: Service readiness status
    Raises:
        HTTPException: 503 if service is not ready
    """
    if generator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"status": "ready", "service": "report-generator"}


@app.post("/generate-report", response_model=ReportResponse)
async def generate_report(request: ReportRequest):
    """
    Generate a structured report.
    This endpoint runs the full report generation workflow and returns
    the final report. It's synchronous (waits for completion).

    Args:
        request: ReportRequest with topic, structure, and options

    Returns:
        ReportResponse with final_report, sections, and metadata

    Raises:
        HTTPException: 500 if generation fails
    """
    start_time = time.time()
    logger.info("Generating report...")

    if generator is None:
        logger.error("Generator not initialized")
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        # Collect all progress events from generator
        final_report = ""
        completed_sections = []

        async for event_type, data in generator.generate_full_report(request):
            if event_type == "status":
                progress = data.get("progress")
                if progress is not None:
                    logger.info("Progress: %d%%", int(progress))

            elif event_type == "complete":
                final_report = data.get("final_report", "")
                completed_sections = [Section(**s) for s in data.get("sections", [])]
                break

            elif event_type == "error":
                logger.error("Report generation error occurred")
                raise HTTPException(status_code=500, detail="Report generation failed")

        # Calculate metadata
        generation_time = time.time() - start_time
        word_count = count_words(final_report)

        logger.info(
            f"Done - Report complete: {len(completed_sections)} sections, "
            f"{word_count} words, {generation_time:.1f}s"
        )

        return ReportResponse(
            topic=request.topic,
            sections=completed_sections,
            final_report=final_report,
            metadata={
                "generation_time_seconds": round(generation_time, 2),
                "section_count": len(completed_sections),
                "total_words": word_count,
            },
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "logging.Formatter",
                "fmt": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
        },
    }

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=log_config)
