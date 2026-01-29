#!/bin/bash

# Airflow development runner
# Keeps AIRFLOW_HOME system-wide but loads DAGs from this project

set -e

# Set system-wide AIRFLOW_HOME
export AIRFLOW_HOME=${AIRFLOW_HOME:-~/airflow}

# Point to project DAGs
export AIRFLOW__CORE__DAGS_FOLDER="$(pwd)/dags"

# Disable example DAGs
export AIRFLOW__CORE__LOAD_EXAMPLES=False

# Initialize DB if needed
if [ ! -f "$AIRFLOW_HOME/airflow.db" ]; then
    echo "Initializing Airflow database..."
    uv run airflow db migrate
fi

# Run standalone
echo "Starting Airflow standalone with DAGs from: $AIRFLOW__CORE__DAGS_FOLDER"
echo "AIRFLOW_HOME: $AIRFLOW_HOME"
uv run airflow standalone
