from airflow import DAG
from airflow.sdk import task
from kubernetes.client import models as k8s


kueue_executor_config = {
    "pod_override": k8s.V1Pod(
        metadata=k8s.V1ObjectMeta(annotations={"kueue.x-k8s.io/queue-name": "airflow"}),
        spec=k8s.V1PodSpec(
            containers=[
                k8s.V1Container(
                    name="base",
                    resources=k8s.V1ResourceRequirements(
                        requests={"memory": "1Gi", "cpu": "250m"},
                        limits={"memory": "1Gi", "cpu": "250m"},
                    ),
                )
            ]
        ),
    )
}

with DAG(
    dag_id="kueue_memory_test2",
    default_args={
        "owner": "airflow",
        "retries": 0,
    },
    max_active_tasks=2,
    max_active_runs=1,
) as dag:

    @task(executor_config=kueue_executor_config)
    def sleep_task(name: str, duration_s: int = 60):
        import time

        print(f"{name}: sleeping {duration_s}s")
        time.sleep(duration_s)
        return name

    sleep_task("task-a")
    sleep_task("task-b")


if __name__ == "__main__":
    dag.test()
