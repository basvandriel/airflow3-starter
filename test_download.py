#!/usr/bin/env python3
"""
Test script that simulates the exact DAG download_large_file_task function.
"""

import asyncio
import logging
import sys
import os

# Add the dags directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dags'))

from utils.download_utils import download_file_optimized_sync, get_file_size_mb

# Set up logging like in the DAG
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_download_large_file_task():
    """Simulate the download_large_file_task from the DAG."""
    workdir = os.path.join(os.path.dirname(__file__), 'workdir')
    os.makedirs(workdir, exist_ok=True)

    # Use a smaller test file for debugging but same logic
    large_file_url = "https://httpbin.org/bytes/52428800"  # 50MB test file
    filename = "test_50mb.bin"

    progress_data = {"last_reported": 0}

    def progress_callback(downloaded, total):
        """Progress callback for large file downloads."""
        # Only log progress every 10MB to avoid spam
        if downloaded - progress_data["last_reported"] >= 10 * 1024 * 1024:
            percent = (downloaded / total) * 100 if total > 0 else 0
            logger.info(f"Download progress: {downloaded}/{total} bytes ({percent:.1f}%)")
            progress_data["last_reported"] = downloaded

    logger.info(f"Starting large file download: {filename}")
    logger.info(f"URL: {large_file_url}")
    logger.info(f"Workdir: {workdir}")
    logger.info("About to call progress callback test...")
    progress_callback(0, 100)  # Test call
    logger.info("Progress callback test completed")

    try:
        # For large files, use optimized download (parallel chunks if supported)
        logger.info("Calling download_file_optimized_sync...")
        filepath = download_file_optimized_sync(
            url=large_file_url,
            filename=filename,
            workdir=workdir,
            chunk_size=1024 * 1024,  # 1MB chunks for large files
            timeout=3600,  # 1 hour timeout
            progress_callback=progress_callback,
        )
        logger.info("Download completed, checking file...")
        size_mb = get_file_size_mb(filepath)
        logger.info(
            f"Successfully downloaded large file: {filepath} ({size_mb:.2f} MB)"
        )
        return filepath
    except Exception as e:
        logger.error(f"Failed to download large file: {e}")
        raise

if __name__ == "__main__":
    test_download_large_file_task()