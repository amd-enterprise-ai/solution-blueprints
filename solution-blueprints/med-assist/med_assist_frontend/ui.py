# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

import gradio as gr
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel
from settings import settings

frontend_logger = logging.getLogger("frontend")
frontend_logger.setLevel(logging.DEBUG)
if not frontend_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    frontend_logger.addHandler(_handler)
    frontend_logger.propagate = False


def build_gradio_ui():
    with gr.Blocks(
        title="Voice consultation",
        theme=gr.themes.Soft(primary_hue="green"),
        css="""
        .link-btn { padding: 1rem 1.5rem; font-size: 1.1rem; text-decoration: none;
                    border-radius: 8px; display: inline-block; margin: 0.25rem; }
        .link-doctor { background: #238636; color: white; }
        .link-doctor:hover { background: #2ea043; color: white; }
        .link-patient { background: #1f6feb; color: white; }
        .link-patient:hover { background: #388bfd; color: white; }
        """,
    ) as demo:
        gr.Markdown(
            """
            ## Voice consultation (LiveKit)
            Choose a role and open the client in a **new tab**. For a conversation you need **two tabs** — one as doctor, one as patient.
            1. Click the link below (opens in a new tab).
            2. Allow microphone access.
            3. Repeat for the second role in another tab.
            """
        )
        with gr.Row():
            gr.HTML(
                '<a href="/client?role=doctor" target="_blank" class="link-btn link-doctor">🩺 Connect as doctor</a>'
            )
            gr.HTML(
                '<a href="/client?role=patient" target="_blank" class="link-btn link-patient">🧑‍⚕️ Connect as patient</a>'
            )
        gr.Markdown(
            """
            ---
            **Requirement:** start LiveKit first: `docker compose up -d` (from project root).
            """
        )
    return demo


CLIENT_DIR = Path(__file__).parent / "client_dist"


def create_app():
    app = FastAPI(title="Voice consultation")

    @app.get("/api/ws-url")
    def api_ws_url():
        """LiveKit URL for the client."""
        return JSONResponse({"wsUrl": settings.livekit_ws_url.encoded_string()})

    @app.get("/api/token")
    def api_token(role: str):
        """Issue JWT for joining the room. role: doctor | patient."""
        if role not in ("doctor", "patient"):
            raise HTTPException(status_code=400, detail="role must be 'doctor' or 'patient'")

        grants = VideoGrants(
            room_join=True,
            room=settings.livekit_room,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
        identity = role
        name = "Doctor" if role == "doctor" else "Patient"
        token = (
            AccessToken(
                api_key=settings.livekit_api_key.get_secret_value(),
                api_secret=settings.livekit_api_secret.get_secret_value(),
            )
            .with_identity(identity)
            .with_name(name)
            .with_grants(grants)
        )
        return JSONResponse({"token": token.to_jwt()})

    class LogEntry(BaseModel):
        level: str = "info"
        message: str
        context: dict | None = None

    _LOG_LEVEL_MAP = {
        "debug": frontend_logger.debug,
        "info": frontend_logger.info,
        "warn": frontend_logger.warning,
        "warning": frontend_logger.warning,
        "error": frontend_logger.error,
    }

    @app.post("/api/log")
    def api_log(entry: LogEntry):
        """Receive a log entry from the React frontend and write it to container stdout."""
        log_fn = _LOG_LEVEL_MAP.get(entry.level.lower(), frontend_logger.info)
        if entry.context:
            log_fn("[frontend] %s | %s", entry.message, entry.context)
        else:
            log_fn("[frontend] %s", entry.message)
        return JSONResponse({"ok": True})

    if (CLIENT_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=CLIENT_DIR / "assets"), name="assets")

    if CLIENT_DIR.is_dir():

        @app.get("/signin-bg.webp")
        def serve_signin_bg():
            path = CLIENT_DIR / "signin-bg.webp"
            if path.exists():
                return FileResponse(path, media_type="image/webp")
            raise HTTPException(status_code=404)

    @app.get("/")
    def serve_root():
        """Serve React app or fallback to old index.html."""
        react_index = CLIENT_DIR / "index.html"
        if react_index.exists():
            return FileResponse(react_index, media_type="text/html")
        return FileResponse(settings.client_html, media_type="text/html")

    @app.get("/client")
    def serve_client():
        """Same as root."""
        react_index = CLIENT_DIR / "index.html"
        if react_index.exists():
            return FileResponse(react_index, media_type="text/html")
        return FileResponse(settings.client_html, media_type="text/html")

    demo = build_gradio_ui()
    app = gr.mount_gradio_app(app, demo, path="/lobby")

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
