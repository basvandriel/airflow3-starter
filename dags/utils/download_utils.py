"""
Utility functions for downloading files in Airflow DAGs.
Optimized for both small and large files.
"""

import os
import requests
import time
from pathlib import Path
from typing import Optional, Callable


def create_workdir(workdir_path: str = "workdir") -> str:
    """
    Create working directory if it doesn't exist.

    Args:
        workdir_path: Path to the working directory

    Returns:
        Absolute path to the working directory
    """
    workdir = Path(workdir_path)
    workdir.mkdir(parents=True, exist_ok=True)
    return str(workdir.absolute())


def download_file(
    url: str, filename: str, workdir: str, chunk_size: int = 8192, timeout: int = 300
) -> str:
    """
    Download a file from URL to the working directory with streaming for large files.

    Args:
        url: URL to download from
        filename: Name for the downloaded file
        workdir: Working directory path
        chunk_size: Size of chunks to download (default 8KB)
        timeout: Request timeout in seconds (default 5 minutes)

    Returns:
        Path to the downloaded file

    Raises:
        requests.RequestException: If download fails
    """
    filepath = os.path.join(workdir, filename)

    # Use streaming for memory efficiency
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)

    return filepath


def download_file_with_progress(
    url: str,
    filename: str,
    workdir: str,
    chunk_size: int = 8192,
    timeout: int = 300,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Download a file with progress monitoring for large files.

    Args:
        url: URL to download from
        filename: Name for the downloaded file
        workdir: Working directory path
        chunk_size: Size of chunks to download
        timeout: Request timeout in seconds
        progress_callback: Optional callback function (downloaded_bytes, total_bytes)

    Returns:
        Path to the downloaded file
    """
    filepath = os.path.join(workdir, filename)

    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))

        downloaded = 0
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

    return filepath


def download_multiple_files(file_specs: list, workdir: str, **kwargs) -> list:
    """
    Download multiple files based on specifications.

    Args:
        file_specs: List of dicts with 'url' and 'filename' keys
        workdir: Working directory path
        **kwargs: Additional arguments passed to download_file

    Returns:
        List of paths to downloaded files
    """
    downloaded_files = []

    for spec in file_specs:
        url = spec["url"]
        filename = spec["filename"]
        filepath = download_file(url, filename, workdir, **kwargs)
        downloaded_files.append(filepath)

    return downloaded_files


def get_file_size_mb(filepath: str) -> float:
    """
    Get file size in MB.

    Args:
        filepath: Path to the file

    Returns:
        File size in MB
    """
    size_bytes = os.path.getsize(filepath)
    return size_bytes / (1024 * 1024)


def cleanup_old_files(workdir: str, max_age_hours: int = 24) -> int:
    """
    Clean up old files in workdir to free up space.

    Args:
        workdir: Working directory path
        max_age_hours: Maximum age of files to keep

    Returns:
        Number of files removed
    """
    workdir_path = Path(workdir)
    cutoff_time = time.time() - (max_age_hours * 3600)
    removed_count = 0

    for file_path in workdir_path.glob("*"):
        if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
            file_path.unlink()
            removed_count += 1

    return removed_count
