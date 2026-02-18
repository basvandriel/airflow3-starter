"""
Utility functions for downloading files in Airflow DAGs.
Optimized for both small and large files.
"""

import os
import asyncio
import aiohttp
import time
from pathlib import Path
from typing import Optional, Callable

import requests


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


async def download_file_with_progress_async(
    url: str,
    filename: str,
    workdir: str,
    chunk_size: int = 8192,
    timeout: int = 300,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Download a file with progress monitoring for large files using aiohttp.

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
    print(f"DEBUG: Starting download of {url} to {filepath}")  # Debug log

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))
            print(f"DEBUG: Total size: {total_size}")  # Debug log

            downloaded = 0
            with open(filepath, "wb") as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            print(
                                f"DEBUG: Calling progress callback: {downloaded}/{total_size}"
                            )  # Debug log
                            progress_callback(downloaded, total_size)

    print(f"DEBUG: Download completed: {filepath}")  # Debug log
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
    Synchronous wrapper for async download function.
    """
    return asyncio.run(
        download_file_with_progress_async(
            url=url,
            filename=filename,
            workdir=workdir,
            chunk_size=chunk_size,
            timeout=timeout,
            progress_callback=progress_callback,
        )
    )


async def check_range_support(url: str, timeout: int = 10) -> bool:
    """
    Check if a server supports HTTP range requests.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        True if range requests are supported
    """
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.head(url) as response:
                return response.headers.get("Accept-Ranges", "").lower() == "bytes"
    except Exception:
        return False


async def download_file_parallel_chunks(
    url: str,
    filename: str,
    workdir: str,
    num_chunks: int = 4,
    chunk_size: int = 8192,
    timeout: int = 300,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Download a file using parallel chunk downloads with HTTP range requests.

    Args:
        url: URL to download from
        filename: Name for the downloaded file
        workdir: Working directory path
        num_chunks: Number of parallel chunks to download
        chunk_size: Size of chunks to download
        timeout: Request timeout in seconds
        progress_callback: Optional callback function (downloaded_bytes, total_bytes)

    Returns:
        Path to the downloaded file
    """
    print(f"DEBUG: Starting parallel chunk download for {url}")  # Debug log
    filepath = os.path.join(workdir, filename)

    # First, get the file size
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        async with session.head(url) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))

    print(f"DEBUG: File size: {total_size} bytes")  # Debug log
    if total_size == 0:
        # Fallback to regular download if we can't get size
        print("DEBUG: File size is 0, falling back to regular download")  # Debug log
        return await download_file_with_progress_async(
            url, filename, workdir, chunk_size, timeout, progress_callback
        )

    # Calculate chunk ranges
    chunk_ranges = []
    chunk_size_bytes = total_size // num_chunks

    for i in range(num_chunks):
        start = i * chunk_size_bytes
        end = (i + 1) * chunk_size_bytes - 1 if i < num_chunks - 1 else total_size - 1
        chunk_ranges.append((start, end))

    print(f"DEBUG: Chunk ranges: {chunk_ranges}")  # Debug log

    async def download_chunk(chunk_range, chunk_index):
        """Download a specific chunk of the file."""
        start, end = chunk_range
        headers = {"Range": f"bytes={start}-{end}"}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.read()
                return chunk_index, data

    # Download all chunks concurrently
    print("DEBUG: Starting concurrent chunk downloads")  # Debug log
    tasks = [
        download_chunk(chunk_range, i) for i, chunk_range in enumerate(chunk_ranges)
    ]
    results = await asyncio.gather(*tasks)

    # Sort results by chunk index and write to file
    results.sort(key=lambda x: x[0])

    print("DEBUG: Combining chunks into final file")  # Debug log
    with open(filepath, "wb") as f:
        downloaded = 0
        for _, data in results:
            f.write(data)
            downloaded += len(data)
            if progress_callback:
                print(
                    f"DEBUG: Calling progress callback: {downloaded}/{total_size}"
                )  # Debug log
                progress_callback(downloaded, total_size)

    print(f"DEBUG: Parallel download completed: {filepath}")  # Debug log
    return filepath


async def download_file_optimized(
    url: str,
    filename: str,
    workdir: str,
    chunk_size: int = 65536,  # Larger chunk size for better throughput
    timeout: int = 300,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Optimized download function that uses parallel chunks if range requests are supported.

    Args:
        url: URL to download from
        filename: Name for the downloaded file
        workdir: Working directory path
        chunk_size: Size of chunks to download
        timeout: Request timeout in seconds
        progress_callback: Optional callback function

    Returns:
        Path to the downloaded file
    """
    print(f"DEBUG: Checking range support for {url}")  # Debug log
    # Check if range requests are supported
    supports_range = await check_range_support(url)
    print(f"DEBUG: Range support: {supports_range}")  # Debug log

    if supports_range:
        print("DEBUG: Using parallel chunk downloads")  # Debug log
        # Use parallel chunk downloads for better performance
        return await download_file_parallel_chunks(
            url,
            filename,
            workdir,
            num_chunks=4,
            chunk_size=chunk_size,
            timeout=timeout,
            progress_callback=progress_callback,
        )
    else:
        print("DEBUG: Using regular async download")  # Debug log
        # Fallback to regular async download
        return await download_file_with_progress_async(
            url, filename, workdir, chunk_size, timeout, progress_callback
        )


async def download_multiple_files_async(
    file_specs: list, workdir: str, **kwargs
) -> list:
    """
    Download multiple files concurrently using aiohttp.

    Args:
        file_specs: List of dicts with 'url' and 'filename' keys
        workdir: Working directory path
        **kwargs: Additional arguments passed to download_file_with_progress_async

    Returns:
        List of paths to downloaded files
    """

    async def download_single_file(spec):
        """Download a single file and return its path."""
        url = spec["url"]
        filename = spec["filename"]
        return await download_file_with_progress_async(url, filename, workdir, **kwargs)

    # Create tasks for concurrent downloads
    tasks = [download_single_file(spec) for spec in file_specs]

    # Run all downloads concurrently
    downloaded_files = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that occurred
    results = []
    for i, result in enumerate(downloaded_files):
        if isinstance(result, Exception):
            raise result  # Re-raise the exception
        results.append(result)

    return results


def download_multiple_files_concurrent(
    file_specs: list, workdir: str, **kwargs
) -> list:
    """
    Download multiple files concurrently (synchronous wrapper).

    Args:
        file_specs: List of dicts with 'url' and 'filename' keys
        workdir: Working directory path
        **kwargs: Additional arguments passed to download functions

    Returns:
        List of paths to downloaded files
    """
    return asyncio.run(download_multiple_files_async(file_specs, workdir, **kwargs))


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


def download_file_optimized_sync(
    url: str,
    filename: str,
    workdir: str,
    chunk_size: int = 65536,
    timeout: int = 300,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Synchronous wrapper for optimized download function.
    """
    return asyncio.run(
        download_file_optimized(
            url=url,
            filename=filename,
            workdir=workdir,
            chunk_size=chunk_size,
            timeout=timeout,
            progress_callback=progress_callback,
        )
    )
