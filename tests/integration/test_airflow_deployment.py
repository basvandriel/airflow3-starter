import json
import subprocess

import pytest

from tests.utils import exec_in_pod, find_pod, wait_for_ready


AIRFLOW_COMPONENTS = [
    "api-server",
    "dag-processor",
    "postgresql",
    "scheduler",
    "statsd",
    "triggerer",
]


@pytest.mark.parametrize("component", AIRFLOW_COMPONENTS)
def test_pod_is_ready(k8s, namespace: str, chart_name: str, component: str) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-{component}")
    assert pod is not None, f"No pod found for component '{component}'"
    assert wait_for_ready(k8s, namespace, pod.metadata.name)


def test_dag_processor_image_is_present(k8s, namespace: str, chart_name: str) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-dag-processor")
    assert pod is not None, "No dag-processor pod found"
    assert pod.spec.containers[0].image, "dag-processor container has no image set"


def test_dag_file_exists_in_pod(k8s, namespace: str, chart_name: str) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-dag-processor")
    assert pod is not None, "No dag-processor pod found"

    contents = exec_in_pod(
        k8s,
        namespace,
        pod.metadata.name,
        container="dag-processor",
        command=["ls", "/opt/airflow/dags/"],
    )
    assert "hello_world.py" in contents
    assert "utils" in contents


def test_logs_pvc_is_bound(k8s, namespace: str) -> None:
    pvc = k8s.read_namespaced_persistent_volume_claim("my-logs-pvc", namespace)
    assert pvc.status.phase == "Bound"


def test_dags_pvc_is_bound_if_present(k8s, namespace: str) -> None:
    try:
        pvc = k8s.read_namespaced_persistent_volume_claim("my-dags-pvc", namespace)
    except Exception as e:  # pragma: no cover
        # kube-agnostic deployments may not have a dags PVC.
        if getattr(e, "status", None) == 404:
            pytest.skip("my-dags-pvc not present (expected for prod)")
        raise
    assert pvc.status.phase == "Bound"


def test_helm_release_is_deployed(namespace: str, chart_name: str) -> None:
    result = subprocess.run(
        ["helm", "status", chart_name, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    status = json.loads(result.stdout)["info"]["status"]
    assert status == "deployed"


def test_kueue_controller_is_running(k8s, kueue_namespace: str) -> None:
    pods = k8s.list_namespaced_pod(kueue_namespace).items
    controller_pods = [p for p in pods if "kueue-controller-manager" in p.metadata.name]
    assert controller_pods
    pod = controller_pods[0]
    ready = any(
        c.type == "Ready" and c.status == "True" for c in (pod.status.conditions or [])
    )
    assert ready


def test_kueue_local_queue_exists(namespace: str) -> None:
    result = subprocess.run(
        ["kubectl", "get", "localqueue", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    queues = json.loads(result.stdout)["items"]
    assert queues


def test_kueue_cluster_queue_exists() -> None:
    result = subprocess.run(
        ["kubectl", "get", "clusterqueue", "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    queues = json.loads(result.stdout)["items"]
    assert queues
