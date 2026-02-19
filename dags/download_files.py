import os
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

# Import our custom utilities
from utils.download_utils import (
    create_workdir,
    download_multiple_files_concurrent,
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
setup_workdir_task >> download_task
download_task >> verify_task
verify_task >> cleanup_task_op

if __name__ == "__main__":
    dag.test()
