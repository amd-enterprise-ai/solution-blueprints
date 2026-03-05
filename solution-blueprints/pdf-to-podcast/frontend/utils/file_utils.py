# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
import logging
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from ..settings import GRADIO_CACHE_DIR, LOG_FILE_PATH, OUTPUT_DIR, UPLOAD_DIR

log = logging.getLogger(__name__)


def read_logs() -> str:
    """Read accumulated logs from the shared log file for UI display.

    Flushes all log handlers and reads the content from the log file.
    If the log file does not exist, returns an empty string.

    Returns:
        str: Content of the log file as a string, or empty string if file doesn't exist.
    """
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception as exc:
            log.warning("Failed to flush log handler %r: %s", handler, exc)

    if LOG_FILE_PATH.exists():
        return LOG_FILE_PATH.read_text(encoding="utf-8")

    return ""


def clear_logs() -> None:
    """Clear the log file.

    Writes an empty string to the log file, effectively clearing all logs.
    """
    LOG_FILE_PATH.write_text("", encoding="utf-8")


def ensure_list(files: str | Path | Iterable[str] | None) -> list[str]:
    """Normalize incoming value to a list of paths (as strings).

    Converts various input types (single path, list, tuple, or None) into
    a list of string paths. Filters out None values from iterables.

    Args:
        files: Single path string, Path object, iterable of paths, or None.

    Returns:
        list[str]: List of path strings. Empty list if input is None.
    """
    if files is None:
        return []
    if isinstance(files, (list, tuple)):
        return [str(f) for f in files if f is not None]
    return [str(files)]


def copy_files_to_upload_dir(file_paths: list[str]) -> list[str]:
    """Copy files from Gradio temp directory to our upload directory.

    Copies each file to the upload directory, handling filename conflicts
    by appending a counter to the filename. Skips files that don't exist
    or fail to copy, logging warnings for such cases.

    Args:
        file_paths: List of source file paths to copy.

    Returns:
        list[str]: List of destination file paths that were successfully copied.
    """
    copied_paths = []

    for file_path in file_paths:
        if not file_path:
            continue
        try:
            file_norm_path = os.path.normpath(file_path)

            if not file_norm_path.startswith(GRADIO_CACHE_DIR):
                # Skip files not in upload directory (e.g., Gradio temp files)
                continue

            source_path = Path(file_norm_path)

            if not source_path.exists():
                log.warning("Source file does not exist: %s", repr(source_path))
                continue

            # Copy to upload directory
            filename = source_path.name
            dest_path = UPLOAD_DIR / filename

            # Handle filename conflicts
            counter = 1

            while dest_path.exists():
                stem = source_path.stem
                suffix = source_path.suffix
                dest_path = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
                counter += 1

            shutil.copy2(source_path, dest_path)
            copied_paths.append(str(dest_path))
            log.debug("Copied %s to %s", repr(source_path), repr(dest_path))
        except Exception as exc:
            log.warning("Failed to copy file %s: %s", repr(file_path), exc)

    return copied_paths


def cleanup_files(paths: list[str]) -> None:
    """Clean up files from upload directory only.

    Removes files from the upload directory. Skips files that are not
    in the upload directory (e.g., Gradio temp files) for safety.
    Logs warnings for files that fail to delete.

    Args:
        paths: List of file paths to delete. Only files in the upload
            directory will be deleted.
    """
    for p in paths:
        try:
            fullpath = os.path.normpath(p)

            if not fullpath.startswith(UPLOAD_DIR.absolute().as_posix()):
                # Skip files not in upload directory (e.g., Gradio temp files)
                continue

            if os.path.exists(fullpath):
                os.remove(fullpath)
                log.debug("Cleaned up file: %s", repr(fullpath))

        except Exception as exc:
            log.warning("Failed to cleanup file %s: %s", repr(p), exc)


def read_pdf_file(file_path: str) -> tuple[str, bytes]:
    """Read a PDF file and return its basename and content.

    Reads a PDF file from the upload directory and returns its filename
    and binary content. Only files in the upload directory are allowed.

    Args:
        file_path: Path to the PDF file.

    Returns:
        tuple[str, bytes]: Tuple containing (basename, file_content).

    Raises:
        Exception: If file is not in the allowed upload directory.
    """
    fullpath = os.path.normpath(file_path)

    if not fullpath.startswith(UPLOAD_DIR.absolute().as_posix()):
        raise Exception("not allowed")

    with open(fullpath, "rb") as f:
        content = f.read()
        return os.path.basename(fullpath), content


def save_transcript(filename: str, transcript_data: dict) -> str:
    """Save transcript JSON to file.

    Saves transcript data as a JSON file in the output directory with
    the format "transcript_{filename}.json".

    Args:
        filename: Base filename (without extension) for the transcript file.
        transcript_data: Dictionary containing transcript data to save.

    Returns:
        str: Absolute path to the saved transcript file.
    """
    filepath = OUTPUT_DIR / f"transcript_{filename}.json"

    with open(filepath, "w") as file:
        json.dump(transcript_data, file, indent=2)
    log.info("Transcript data saved to %s", filepath)
    return filepath.absolute().as_posix()


def create_empty_transcript(filename: str) -> str:
    """Create an empty transcript file with a note.

    Creates a transcript JSON file with a note indicating that the transcript
    endpoint is not available or the transcript was not found.

    Args:
        filename: Base filename (without extension) for the transcript file.

    Returns:
        str: Absolute path to the created transcript file.
    """
    filepath = OUTPUT_DIR / f"transcript_{filename}.json"

    with open(filepath, "w") as file:
        json.dump({"note": "Transcript endpoint not available or transcript not found"}, file)
    return filepath.absolute().as_posix()


def save_audio_file(output_id: str, audio_content: bytes) -> Path:
    """Save audio content to file.

    Saves audio content as an MP3 file in the output directory with
    the format "{output_id}-output.mp3".

    Args:
        output_id: Unique identifier for the output file.
        audio_content: Audio file content as bytes.

    Returns:
        Path: Path object pointing to the saved audio file.
    """
    output_path = OUTPUT_DIR / f"{output_id}-output.mp3"

    with open(output_path, "wb") as f:
        f.write(audio_content)
    log.info("Audio file saved as '%s'", output_path)
    return output_path
