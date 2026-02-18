"""
DAG for downloading files from the internet using Python operators.
Demonstrates modular design with utility functions and large file handling.
"""

import os
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

# Import our custom utilities
from utils.download_utils import (
    create_workdir,
    download_multiple_files_concurrent,
    download_file_optimized_sync,
    get_file_size_mb,
    cleanup_old_files,
)

# Set up logging
logger = logging.getLogger(__name__)

# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # Increase timeout for large file downloads
    "execution_timeout": timedelta(hours=2),
}

# Define the DAG
dag = DAG(
    "download_files",
    default_args=default_args,
    description="Download files from internet using Python operators",
    schedule=timedelta(days=1),
    catchup=False,
    # Add tags for better organization
    tags=["download", "files", "large-files"],
)


def setup_workdir(**context):
    """Create working directory and return its path."""
    workdir = create_workdir("workdir")
    logger.info(f"Created working directory: {workdir}")
    # Store workdir in XCom for use by other tasks
    context["ti"].xcom_push(key="workdir", value=workdir)
    return workdir


def download_files_task(**context):
    """Download multiple files from the internet."""
    # Get workdir from previous task
    workdir = context["ti"].xcom_pull(task_ids="setup_workdir", key="workdir")

    # Define files to download (using sample URLs)
    file_specs = [
        {"url": "https://httpbin.org/json", "filename": "sample1.json"},
        {"url": "https://httpbin.org/xml", "filename": "sample2.xml"},
    ]

    logger.info(f"Downloading files to: {workdir}")
    downloaded_files = download_multiple_files_concurrent(file_specs, workdir)

    logger.info(f"Downloaded {len(downloaded_files)} files:")
    for filepath in downloaded_files:
        size_mb = get_file_size_mb(filepath)
        logger.info(f"  - {filepath} ({size_mb:.2f} MB)")

    return downloaded_files


def download_large_file_task(**context):
    """Download a large file with progress monitoring."""
    workdir = context["ti"].xcom_pull(task_ids="setup_workdir", key="workdir")

    # Example: Download a large test file (Ubuntu ISO for demo - replace with your actual large file)
    # For testing, we'll use a smaller file but demonstrate the pattern
    large_file_url = "https://vault.centos.org/7.9.2009/isos/x86_64/CentOS-7-x86_64-DVD-2009.iso"  # ~4GB file
    filename = "centos.iso"

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


def cleanup_task(**context):
    """Clean up old files to free disk space."""
    workdir = context["ti"].xcom_pull(task_ids="setup_workdir", key="workdir")

    logger.info(f"Cleaning up old files in {workdir}")
    removed_count = cleanup_old_files(workdir, max_age_hours=24)

    logger.info(f"Removed {removed_count} old files")

    return removed_count


def verify_downloads(**context):
    """Verify that files were downloaded successfully."""
    downloaded_files = context["ti"].xcom_pull(task_ids="download_files_task")

    logger.info(f"Verifying {len(downloaded_files)} downloaded files:")
    for filepath in downloaded_files:
        if os.path.exists(filepath):
            size_mb = get_file_size_mb(filepath)
            logger.info(f"  ✓ {filepath} ({size_mb:.2f} MB)")
        else:
            raise FileNotFoundError(f"File not found: {filepath}")


# Define the tasks
setup_workdir_task = PythonOperator(
    task_id="setup_workdir",
    python_callable=setup_workdir,
    dag=dag,
)

download_task = PythonOperator(
    task_id="download_files_task",
    python_callable=download_files_task,
    dag=dag,
)

download_large_task = PythonOperator(
    task_id="download_large_file",
    python_callable=download_large_file_task,
    dag=dag,
)

cleanup_task_op = PythonOperator(
    task_id="cleanup_old_files",
    python_callable=cleanup_task,
    dag=dag,
)

verify_task = PythonOperator(
    task_id="verify_downloads",
    python_callable=verify_downloads,
    dag=dag,
)

# Set task dependencies
setup_workdir_task >> [download_task, download_large_task]
download_task >> verify_task
[verify_task, download_large_task] >> cleanup_task_op
