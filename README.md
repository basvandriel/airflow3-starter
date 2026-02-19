# Airflow 3 Starter Project

This is a starter project for Apache Airflow 3 using UV for dependency management.

## Setup

1. Ensure you have UV installed: `pip install uv`
2. Clone or navigate to this project
3. Install dependencies: `uv sync`

## Running Locally

To start Airflow in standalone mode (includes webserver and scheduler):

```bash
AIRFLOW_HOME=. AIRFLOW__CORE__LOAD_EXAMPLES=False uv run airflow standalone
```

This will:
- Set AIRFLOW_HOME to the current directory
- Disable loading of example DAGs
- Initialize the SQLite database (if not already done)
- Start the webserver on http://localhost:8080
- Start the scheduler

## Alternative: System-wide AIRFLOW_HOME with Project DAGs

If you prefer a system-wide AIRFLOW_HOME (like `~/airflow`) while keeping DAGs in this repo (similar to Dagster's approach):

Use the provided `run.sh` script:

```bash
./run.sh
```

This script:
- Sets `AIRFLOW_HOME=~/airflow` (or uses existing `AIRFLOW_HOME` env var)
- Points `AIRFLOW__CORE__DAGS_FOLDER` to `./dags`
- Disables example DAGs (`AIRFLOW__CORE__LOAD_EXAMPLES=False`)
- Initializes the database if needed
- Runs `airflow standalone`

Or manually:
```bash
AIRFLOW_HOME=~/airflow AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags AIRFLOW__CORE__LOAD_EXAMPLES=False uv run airflow standalone
```

This keeps the database, logs, and config in `~/airflow`, but loads DAGs from your project's `dags/` directory.

## Accessing the UI

Open http://localhost:8080 in your browser.

Default credentials:
- Username: admin
- Password: admin

## DAGs

Place your DAG files in the `dags/` directory.

A sample `hello_world.py` DAG is included.

### Advanced Example: download_files.py

A more complex DAG that demonstrates best practices:

- **Modular design**: Business logic separated into `dags/utils/download_utils.py`
- **Python operators**: Uses `PythonOperator` for custom logic
- **XCom communication**: Tasks pass data between each other
- **Error handling**: Proper exception handling and verification
- **Large file support**: Streaming downloads, progress monitoring, timeouts
- **Resource management**: Automatic cleanup of old files

The DAG includes multiple tasks:
1. **setup_workdir**: Creates working directory
2. **download_files_task**: Downloads small sample files
3. **download_large_file**: Downloads large files (3GB+) with progress monitoring
4. **verify_downloads**: Confirms files exist and shows sizes
5. **cleanup_old_files**: Removes files older than 24 hours

**Large File Considerations:**
- Uses streaming downloads to avoid memory issues
- Configurable chunk sizes (1MB for large files)
- Progress callbacks for monitoring
- Extended timeouts (2 hours per task)
- Automatic cleanup to manage disk space

Run it manually from the UI or trigger it to see the modular approach in action.

## Best Practices

- Use virtual environments (handled by UV)
- Keep DAGs simple and testable
- Use Airflow's built-in testing tools
- For production, use proper databases and configurations

## Stopping

Press Ctrl+C to stop the standalone server.


### Debugging with dag.test()

1. (If port is busy) Kill port 5683:
```bash
docker compose exec -T airflow-worker python /opt/airflow/dags/utils/kill_port.py 5683
```

2. Start debugpy in the worker (blocks until VS Code attaches):
```bash
docker compose exec -T airflow-worker python -Xfrozen_modules=off -m debugpy --log-to-stderr --log-to /tmp/debugpy-logs --listen 0.0.0.0:5683 --wait-for-client /opt/airflow/dags/utils/debug_runner.py /opt/airflow/dags/download_files.py
```

3. Set breakpoints in the DAG file, then press **F5** with `Airflow: Debug Tasks (active file)`.