# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse
from flow import CreateDocumentationFlow
from pydantic import BaseModel
from state import documentation_status
from werkzeug.utils import secure_filename

# Setup base logging
formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(fmt=formatter)
logger = logging.getLogger("backend")
logger.setLevel(level=logging.INFO)
logger.addHandler(handler)

# Directories preset — anchored to this file's directory so paths are stable
# regardless of the working directory when `python3 -m main` is invoked.
_BASE_DIR = Path(__file__).resolve().parent

REPOSITORIES_ROOT = _BASE_DIR / "repositories"
REPOSITORIES_ROOT.mkdir(parents=True, exist_ok=True)

DOCUMENTATIONS_ROOT = _BASE_DIR / "documentations"
DOCUMENTATIONS_ROOT.mkdir(parents=True, exist_ok=True)

# Fast API
app = FastAPI(title="Code Docs Builder", description="API service for the Code Docs Builder project")


# DTO
class CloneRequest(BaseModel):
    """
    Request model used when initiating a repository clone operation.

    Attributes:
        repo_url: The full URL of the Git repository to be cloned.
    """

    repo_url: str


class CloneResponse(BaseModel):
    """
    Response model returned after a repository has been cloned.

    Attributes:
        repo_id: Unique identifier assigned to the cloned repository. This ID is used for further operations such as
                 documentation generation or retrieval.
    """

    repo_id: str


class GenerateDocumentationResponse(BaseModel):
    """
    Response model returned when documentation generation is started.

    Attributes:
        repo_id: Unique identifier of the repository for which documentation generation was initiated.
        status: String describing the current state of the request. Typically, indicates that planning and documentation
                generation have been queued.
    """

    repo_id: str
    status: str


# Endpoints
@app.post("/repos")
def clone_repo(request: CloneRequest):
    """
    Clone a remote Git repository and store it under a unique repository ID.
    Args:
        request (CloneRequest): Incoming request containing the Git repository URL.
    Returns:
        CloneResponse: Object containing the generated repository ID.
    Raises:
        HTTPException: Returned with status 400 if the cloning process fails.
    """

    # Generates a unique identifier for the cloned repository
    repo_id = str(uuid.uuid4())

    # Sanitize the repo_name to avoid path traversal and other filesystem attacks
    repo_name = secure_filename(request.repo_url.split("/")[-1])

    # Construct the full path where the repository will be stored, then normalize
    repo_path = Path(REPOSITORIES_ROOT / repo_id / repo_name)
    repo_path = repo_path.resolve()
    # Make sure repo_path is within REPOSITORIES_ROOT
    if not str(repo_path).startswith(str(REPOSITORIES_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Invalid repository name specified.")
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning repository: %s", repo_name)
    try:
        # Execute the Git clone command with output captured for error handling
        subprocess.run(["git", "clone", request.repo_url, str(repo_path)], check=True, capture_output=True, text=True)
        logger.info("Cloning repository '%s' success", repo_name)
    except subprocess.CalledProcessError as e:
        # Raise an HTTP exception with Git's stderr output if cloning fails
        raise HTTPException(status_code=400, detail=f"An error occurred while cloning repository: {e.stderr}")

    # Return the unique ID for referencing this cloned repository
    return CloneResponse(repo_id=repo_id)


@app.post(
    "/repos/{repo_id}/documentation/generate",
    response_model=GenerateDocumentationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_documentation_generation(repo_id: str, background_tasks: BackgroundTasks):
    """
    Start background documentation generation for a repository.

    This endpoint:
        - Validates that the repository exists.
        - Queues a background task that performs documentation planning and generation.
        - Immediately returns a 202 Accepted response with basic status info.

    Args:
        repo_id (str): Identifier of the repository for which documentation should be generated.
        background_tasks (BackgroundTasks): FastAPI BackgroundTasks instance used to schedule asynchronous execution.

    Returns:
        GenerateDocumentationResponse: Contains the repository ID and a status message.

    Raises:
        HTTPException (404): If no repository is associated with the given repo_id.

    Notes:
        - The actual work happens asynchronously; this endpoint always responds quickly.
        - The caller can later query documentation availability through another endpoint.
    """
    # Check if documentation generation already started or completed
    status = documentation_status.get(repo_id)
    if status and status != "Failed":
        return _create_generate_documentation_response(status_code=200, status=status, repo_id=repo_id)

    # Validate that repo_id is a valid UUID and does not contain path separators
    try:
        repo_uuid = uuid.UUID(repo_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail=f"No repository found associated with following ID {repo_id}")

    # Normalize the path and ensure it stays within REPOSITORIES_ROOT
    repositories_root_resolved = REPOSITORIES_ROOT.resolve()
    repo_root = (repositories_root_resolved / str(repo_uuid)).resolve()

    # Check that the resolved path is strictly under the repositories root directory, by verifying the common path is
    # repositories_root_resolved
    if not repo_root.is_relative_to(repositories_root_resolved) or not repo_root.exists():
        # Path traversal or repo_id tries to escape the allowed root or simply not found
        logger.info("Incorrect path relations for repository with ID '%s'", repo_uuid)
        raise HTTPException(status_code=404, detail=f"No repository found associated with following ID {repo_id}")

    # Schedule asynchronous execution
    documentation_status[repo_id] = "Processing"
    logger.info("Processing repository: %s", repo_uuid)
    background_tasks.add_task(_plan_and_generate_docs_job, repo_id)

    return _create_generate_documentation_response(
        status_code=202, status="Documentation generation started", repo_id=repo_id
    )


@app.get("/repos/{repo_id}/documentation/status")
def get_documentation_status(repo_id: str):
    """
    Get the current documentation generation status for a specific repository.

    This endpoint returns the last known status of the documentation generation
    process for the provided repository ID. If no documentation process has ever
    been triggered for this repository, a 404 error is returned.

    Args:
        repo_id (str): Identifier of the repository whose documentation status is requested.

    Returns:
        JSONResponse: JSON object containing the fields repo_id and status

    Raises:
        HTTPException (404): If documentation has not been previously generated for the given repository.
    """
    status = documentation_status.get(repo_id)
    if not status:
        raise HTTPException(
            status_code=404, detail="Documentation generation has not been previously run for the provided repository"
        )

    return _create_generate_documentation_response(status_code=200, status=status, repo_id=repo_id)


@app.get("/repos/{repo_id}/documentation")
def get_documentation(repo_id: str):
    """
    Return a single combined Markdown file containing all MDX documentation
    for the given repository.

    This endpoint:
        - Validates that the documentation directory for the repository exists.
        - Recursively collects all `.mdx` files.
        - Concatenates their contents into one Markdown document separated by horizontal rules (`---`).
        - Returns the result as a downloadable `.md` file.

    Args:
        repo_id: Unique repository identifier.

    Returns:
        Response: HTTP response containing a combined Markdown document.

    Raises:
        HTTPException:
            - 404 if the documentation directory does not exist.
            - 404 if no MDX files were found.
    """
    safe_repo_id = secure_filename(repo_id)
    docs_root = DOCUMENTATIONS_ROOT.resolve()
    repo_docs_dir = (docs_root / safe_repo_id).resolve()
    try:
        repo_docs_dir.relative_to(docs_root)
    except ValueError:
        # This means the repo_docs_dir is not within docs_root (path traversal attempt)
        raise HTTPException(
            status_code=404,
            detail="Invalid repository identifier (disallowed path traversal attempt)",
        )

    if not repo_docs_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Documentation for repository with ID '{safe_repo_id}' not ready yet",
        )

    mdx_docs = sorted(repo_docs_dir.rglob("*.mdx"))

    if not mdx_docs:
        raise HTTPException(
            status_code=404,
            detail="No documentation files exist",
        )

    parts: list[str] = []

    for file_path in mdx_docs:
        relative = file_path.relative_to(repo_docs_dir)
        parts.append(f"<!-- Source: {relative.as_posix()} -->\n")

        content = file_path.read_text(encoding="utf-8")
        parts.append(content)

        # Separator between documents
        parts.append("\n\n---\n\n")

    combined_markdown = "\n".join(parts).strip() + "\n"

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_repo_id}_docs.md"',
    }

    return Response(
        content=combined_markdown,
        media_type="text/markdown",
        headers=headers,
    )


def _create_generate_documentation_response(status_code: int, status: str, repo_id: str):
    """
    Create a standardized JSON response for documentation generation processes.

    Args:
        status_code (int): HTTP status code to return.
        status (str): Status of the documentation generation process.
        repo_id (str): Identifier of the repository for which documentation was generated.

    Returns:
        JSONResponse: A JSON response with repo_id and status
    """
    body = {"repo_id": repo_id, "status": status}

    return JSONResponse(status_code=status_code, content=body, media_type="application/json")


def _plan_and_generate_docs_job(repo_id: str) -> None:
    """
    Background job responsible for planning and generating documentation for a repository.

    This function:
        - Validates that the repository exists and has been cloned.
        - Locates the actual repository directory for the given repo_id.
        - Initializes the CreateDocumentationFlow with appropriate settings.
        - Executes the full documentation workflow (planning + generation).

    Args:
        repo_id (str): Identifier of the repository whose documentation should be generated.

    Returns:
        None. The result is persisted to the documentation directory on disk.

    Notes:
        - This function is executed asynchronously via FastAPI BackgroundTasks.
        - All errors are logged to stdout; no exceptions propagate back to the API caller.
    """
    repo_root = REPOSITORIES_ROOT / repo_id
    if not repo_root.exists():
        logger.info("No repository found with ID: %s", repo_id)
        return

    # The cloned repository resides in a subdirectory (created by `git clone`)
    subdirs = [p for p in repo_root.iterdir() if p.is_dir()]
    if not subdirs:
        logger.info("Error while processing '%s' repository. Repository has not been cloned.", repo_id)
        return

    repo_path = subdirs[0]

    # Initialize and execute the documentation flow (planning + generation)
    flow = CreateDocumentationFlow(repo_id=repo_id, repo_path=repo_path, docs_path=DOCUMENTATIONS_ROOT)
    flow.run()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8091))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
