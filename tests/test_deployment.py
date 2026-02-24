import json
import subprocess
import time

import pytest
from kubernetes.client import CoreV1Api, V1Pod
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream

POD_READY_TIMEOUT = 60   # seconds
E2E_TIMEOUT = 120        # seconds

AIRFLOW_COMPONENTS = [
    "api-server",
    "dag-processor",
    "postgresql",
    "scheduler",
    "statsd",
    "triggerer",
]


def find_pod(k8s: CoreV1Api, namespace: str, name_prefix: str) -> V1Pod | None:
    return next(
        (p for p in k8s.list_namespaced_pod(namespace).items
         if p.metadata.name.startswith(name_prefix)),
        None,
    )


def pod_is_ready(pod: V1Pod) -> bool:
    return bool(
        pod.status
        and pod.status.conditions
        and any(c.type == "Ready" and c.status == "True" for c in pod.status.conditions)
    )


def wait_for_ready(
    k8s: CoreV1Api, namespace: str, pod_name: str, timeout: int = POD_READY_TIMEOUT
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pod_is_ready(k8s.read_namespaced_pod(pod_name, namespace)):
            return True
        time.sleep(2)
    return False


def exec_in_pod(
    k8s: CoreV1Api, namespace: str, pod_name: str, container: str, command: list[str]
) -> str:
    return stream(
        k8s.connect_get_namespaced_pod_exec,
        pod_name, namespace,
        container=container, command=command,
        stderr=True, stdin=False, stdout=True, tty=False,
    )


@pytest.mark.parametrize("component", AIRFLOW_COMPONENTS)
def test_pod_is_ready(k8s: CoreV1Api, namespace: str, chart_name: str, component: str) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-{component}")
    assert pod is not None, f"No pod found for component '{component}'"
    assert wait_for_ready(k8s, namespace, pod.metadata.name), (
        f"Pod '{pod.metadata.name}' did not become Ready within {POD_READY_TIMEOUT}s"
    )


def test_dag_processor_image_is_present(k8s: CoreV1Api, namespace: str, chart_name: str) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-dag-processor")
    assert pod is not None, "No dag-processor pod found"
    assert pod.spec.containers[0].image, "dag-processor container has no image set"


def test_dag_processor_uses_custom_image(
    k8s: CoreV1Api, namespace: str, chart_name: str, expect_custom_image: bool
) -> None:
    if not expect_custom_image:
        pytest.skip("--expect-custom-image not set")

    pod = find_pod(k8s, namespace, f"{chart_name}-dag-processor")
    assert pod is not None, "No dag-processor pod found"
    image = pod.spec.containers[0].image
    assert not image.startswith("apache/airflow"), (
        f"Expected a custom image but got upstream image: {image}"
    )


@pytest.mark.parametrize("expected", ["hello_world.py", "utils"])
def test_dag_file_exists_in_pod(
    k8s: CoreV1Api, namespace: str, chart_name: str, expected: str
) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-dag-processor")
    assert pod is not None, "No dag-processor pod found"

    contents = exec_in_pod(
        k8s, namespace, pod.metadata.name,
        container="dag-processor", command=["ls", "/opt/airflow/dags/"],
    )
    assert expected in contents, (
        f"'{expected}' not found in /opt/airflow/dags/.\nContents: {contents.strip()}"
    )


def test_logs_pvc_is_bound(k8s: CoreV1Api, namespace: str) -> None:
    pvc = k8s.read_namespaced_persistent_volume_claim("my-logs-pvc", namespace)
    assert pvc.status.phase == "Bound", f"my-logs-pvc phase is '{pvc.status.phase}'"


def test_dags_pvc_is_bound_if_present(k8s: CoreV1Api, namespace: str) -> None:
    try:
        pvc = k8s.read_namespaced_persistent_volume_claim("my-dags-pvc", namespace)
    except ApiException as e:
        if e.status == 404:
            pytest.skip("my-dags-pvc not present (expected for prod)")
        raise
    assert pvc.status.phase == "Bound", f"my-dags-pvc phase is '{pvc.status.phase}'"


def test_helm_release_is_deployed(namespace: str, chart_name: str) -> None:
    result = subprocess.run(
        ["helm", "status", chart_name, "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"helm status failed: {result.stderr.strip()}"
    status = json.loads(result.stdout)["info"]["status"]
    assert status == "deployed", f"Helm release status is '{status}', expected 'deployed'"


def test_e2e_hello_world(k8s: CoreV1Api, namespace: str, chart_name: str, e2e: bool) -> None:
    if not e2e:
        pytest.skip("--e2e not set")

    api_pod = find_pod(k8s, namespace, f"{chart_name}-api-server")
    assert api_pod is not None, "No api-server pod found"

    output = exec_in_pod(
        k8s, namespace, api_pod.metadata.name,
        container="api-server", command=["airflow", "dags", "trigger", "hello_world"],
    )
    assert "queued" in output or "triggered" in output, (
        f"DAG trigger did not return 'queued'.\nOutput: {output}"
    )

    deadline = time.time() + E2E_TIMEOUT
    seen_pod = False

    while time.time() < deadline:
        time.sleep(5)
        task_pods = [
            p for p in k8s.list_namespaced_pod(namespace).items
            if "hello" in p.metadata.name and p.status.phase != "Terminating"
        ]

        if task_pods:
            seen_pod = True
            phase = task_pods[0].status.phase
            if phase == "Succeeded":
                return
            if phase == "Failed":
                pytest.fail(f"Task pod failed (phase: {phase})")
        elif seen_pod:
            return  # pod gone after auto-delete (DELETE_WORKER_PODS=True)

    pytest.fail(f"hello_world did not complete within {E2E_TIMEOUT}s (pod seen: {seen_pod})")
