# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
import os
import sys
import time
import urllib.parse

import requests
from agentic_translation import select_translate_method
from flask import Flask, Response, request, stream_with_context
from langchain.chat_models import init_chat_model

INIT_RETRIES = 10

app = Flask(__name__)

llm = None


def init_llm():
    """Initialize the LLM

    Fetches the model information from the model listing endpoint"""
    global llm
    for retry in range(INIT_RETRIES):
        if retry != 0:
            print(
                "Couldn't retrieve model name - AIM probably not up yet. Waiting 2 seconds...",
                file=sys.stderr,
            )
            time.sleep(2)
        print(f"Trying to retrieve model name (attempt {retry+1})", file=sys.stderr)
        try:
            r = requests.get(urllib.parse.urljoin(os.environ["OPENAI_API_BASE_URL"], "v1/models"), timeout=0.5)
            if r.status_code == 200:
                try:
                    model_name = r.json()["data"][0]["id"]
                    llm = init_chat_model(
                        model=model_name,
                        model_provider="openai",
                        base_url=os.environ["OPENAI_API_BASE_URL"],
                        api_key="dummy",
                    )
                    break
                except (requests.exceptions.JSONDecodeError, KeyError, IndexError):
                    print(f"Invalid response format: {r.content}", file=sys.stderr)
                    raise RuntimeError(f"Failed to retrieve model name, Invalid response format: {r.content}")
        except requests.exceptions.ConnectionError:
            # AIM not available yet
            pass
    else:
        raise RuntimeError("Failed to retrieve model name")


@app.route("/health", methods=["GET"])
def health_check():
    return Response("OK", status=200)


@app.route("/readiness", methods=["GET"])
def readiness_check():
    # check if LLM is available
    try:
        r = requests.get(urllib.parse.urljoin(os.environ["OPENAI_API_BASE_URL"], "v1/models"), timeout=0.5)
        if r.status_code == 200:
            return Response("OK", status=r.status_code)
        return Response(r.content, status=r.status_code)
    except requests.exceptions.RequestException:
        return Response(status=500)


@app.route("/translate", methods=["POST"])
def translate():
    """Translate the source_text from source_language to target_language."""
    try:
        data = request.get_json()
        missing_fields = []
        if "context" not in data:
            missing_fields.append("context")
        else:
            for field in ["source_language", "target_language", "source_text"]:
                if field not in data["context"]:
                    missing_fields.append(f"context.{field}")

        if missing_fields:
            print("Received invalid JSON payload:", data, file=sys.stderr)
            return Response(
                f"Missing required fields in JSON payload: {', '.join(missing_fields)}",
                status=400,
            )
    except Exception as e:
        print(f"Failed to parse JSON payload: {e}", file=sys.stderr)
        return Response("Failed to parse JSON payload", status=400)

    if llm is None:
        try:
            init_llm()
        except Exception as e:
            print(f"Failed to initialize LLM: {e}", file=sys.stderr)
            return Response("Failed to initialize LLM", status=500)

    def generate():
        for agent, content in select_translate_method(llm=llm, **data):
            yield json.dumps({"agent": agent, "content": content})

    try:
        return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
    except Exception as e:
        print(f"Failed to generate response: {e}", file=sys.stderr)
        return Response("Failed to generate response due to internal error", status=500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ["API_PORT"]))
