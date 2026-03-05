# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import sys
import uuid
from typing import Optional, Tuple

import gradio as gr
import requests

# Setup base logging
formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(fmt=formatter)
logger = logging.getLogger("frontend")
logger.setLevel(level=logging.INFO)
logger.addHandler(handler)


class ApiClient:
    """
    HTTP client for interacting with the Code Documentation API.

    This client provides high-level helper methods for:
    - cloning repositories,
    - starting documentation generation,
    - fetching generated documentation.

    Attributes:
        base_url: Base URL of the backend API (e.g. "http://127.0.0.1:8091").
        timeout: Default timeout (in seconds) for HTTP requests.
    """

    def __init__(self, base_url, timeout: int = 60):
        self.base_url = base_url
        self.timeout = timeout

    def clone_repository(self, repo_url: str) -> Tuple[str, str]:
        """
        Clone a Git repository via the backend API.

        Args:
            repo_url: Full URL of the Git repository to clone.

        Returns:
            Tuple[Optional[str], str]:
                - repo_id or None on error,
                - human-readable status message.
        """
        if not repo_url:
            return "", "Provide repository URL"

        try:
            response = requests.post(f"{self.base_url}/repos", json={"repo_url": repo_url}, timeout=120)
        except requests.RequestException:
            gr.Error(message="Back-end is not up yet. Try again later.", duration=5)
            return "", "An error occurred while cloning repository. Back-end is not up yet."

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            return "", f"An error occurred while cloning repository. {detail}"

        data = response.json()
        repo_id = data.get("repo_id")

        return repo_id, f"Repository cloned successfully. Repo ID: {repo_id}"

    def start_generation(self, repo_id: str) -> str:
        """
        Start asynchronous documentation generation for a given repository.

        Args:
            repo_id: Identifier of the repository.

        Returns:
            str: Human-readable status message.
        """
        try:
            repo_uuid = uuid.UUID(repo_id)
        except (ValueError, AttributeError):
            return "Please provide correct repository ID before starting documentation generation."

        status_endpoint = f"{self.base_url}/repos/{repo_uuid}/documentation/status"
        generation_endpoint = f"{self.base_url}/repos/{repo_uuid}/documentation/generate"

        try:
            status_response = requests.get(status_endpoint, timeout=self.timeout)
            if status_response.status_code == 200 and status_response.json().get("status") == "Documentation is ready":
                gr.Info(message="Documentation is ready", duration=5)
                return "Documentation is ready"

            generation_response = requests.post(generation_endpoint, timeout=self.timeout)
        except requests.RequestException:
            gr.Error(
                message="Documentation generation request failed. This might occur if LLM is not yet initialized. Try again later.",
                duration=5,
            )
            return "Request failed while starting documentation generation. This might occur if LLM is not yet initialized. Try again later."

        if generation_response.status_code not in (200, 202):
            detail = self._extract_error_detail(generation_response)
            gr.Error(message=detail, duration=5)
            return f"Error occurred while starting documentation generation: {detail}"

        status = generation_response.json().get("status")
        return status

    def get_documentation_status(self, repo_id: str) -> str:
        try:
            repo_uuid = uuid.UUID(repo_id)
        except (ValueError, AttributeError):
            gr.Error(message="Please provide correct repository ID before fetching documentation status.", duration=5)
            return "Please provide correct repository ID before fetching documentation status."

        try:
            endpoint = f"{self.base_url}/repos/{repo_uuid}/documentation/status"
            response = requests.get(endpoint, timeout=self.timeout)

            if response.status_code != 200:
                return "Error occurred while fetching documentation status"

            return response.json().get("status")
        except requests.RequestException as exc:
            gr.Error(message="Error occurred while fetching documentation status", duration=5)
            return "Error occurred while fetching documentation status"

    def fetch_documentation(self, repo_id: str) -> Tuple[Optional[str], str, str]:
        """
        Fetch generated documentation as Markdown text.

        Args:
            repo_id: Identifier of the repository.

        Returns:
            Tuple[Optional[str], str, str]:
                - filename suggestion (for downloads) or None on error,
                - markdown text (empty string on error),
                - human-readable status message.
        """
        try:
            repo_uuid = uuid.UUID(repo_id)
        except (ValueError, AttributeError):
            return None, "", "Please provide a repository ID before fetching documentation."

        try:
            endpoint = f"{self.base_url}/repos/{repo_uuid}/documentation"
            response = requests.get(endpoint, timeout=self.timeout)
        except requests.RequestException:
            gr.Error(message="Request failed while fetching documentation. Backend is not up.", duration=5)
            return None, "", "Request failed while fetching documentation. Backend is not up yet"

        if response.status_code != 200:
            detail = self._extract_error_detail(response)
            gr.Error(message=f"Error occurred while fetching documentation: {detail}", duration=5)
            return None, "", f"Error occurred while fetching documentation: {detail}"

        markdown_text = response.text
        filename = f"{repo_id}_docs.md"

        return filename, markdown_text, "Documentation successfully fetched."

    @staticmethod
    def _extract_error_detail(response: requests.Response) -> str:
        """
        Extract an error detail from an HTTP response, if possible.

        Args:
            response: HTTP response instance.

        Returns:
            str: Extracted error detail or raw text.
        """
        try:
            data = response.json()
            return data.get("detail", response.text)
        except Exception:
            return response.text
