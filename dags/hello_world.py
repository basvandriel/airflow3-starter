from datetime import datetime, timedelta
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    "hello_world",
    default_args=default_args,
    description="A simple hello world DAG",
    schedule=timedelta(days=1),
    catchup=False,
)

# Define the task
hello_task = BashOperator(
    task_id="hello_task",
    bash_command='echo "Hello, World!"',
    dag=dag,
)
