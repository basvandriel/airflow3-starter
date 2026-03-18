import json
import subprocess
import time
import yaml

import pytest
from kubernetes import client as k8s_client
from kubernetes.client import CoreV1Api, V1Pod
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream

POD_READY_TIMEOUT = 60  # seconds
E2E_TIMEOUT = 120  # seconds

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
        (
            p
            for p in k8s.list_namespaced_pod(namespace).items
            if p.metadata.name.startswith(name_prefix)
        ),
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
        pod_name,
        namespace,
        container=container,
        command=command,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )


@pytest.mark.parametrize("component", AIRFLOW_COMPONENTS)
def test_pod_is_ready(
    k8s: CoreV1Api, namespace: str, chart_name: str, component: str
) -> None:
    pod = find_pod(k8s, namespace, f"{chart_name}-{component}")
    assert pod is not None, f"No pod found for component '{component}'"
    assert wait_for_ready(k8s, namespace, pod.metadata.name), (
        f"Pod '{pod.metadata.name}' did not become Ready within {POD_READY_TIMEOUT}s"
    )


def test_dag_processor_image_is_present(
    k8s: CoreV1Api, namespace: str, chart_name: str
) -> None:
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
        k8s,
        namespace,
        pod.metadata.name,
        container="dag-processor",
        command=["ls", "/opt/airflow/dags/"],
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
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"helm status failed: {result.stderr.strip()}"
    status = json.loads(result.stdout)["info"]["status"]
    assert status == "deployed", (
        f"Helm release status is '{status}', expected 'deployed'"
    )


def test_e2e_hello_world(
    k8s: CoreV1Api, namespace: str, chart_name: str, e2e: bool
) -> None:
    if not e2e:
        pytest.skip("--e2e not set")

    api_pod = find_pod(k8s, namespace, f"{chart_name}-api-server")
    assert api_pod is not None, "No api-server pod found"

    output = exec_in_pod(
        k8s,
        namespace,
        api_pod.metadata.name,
        container="api-server",
        command=["airflow", "dags", "trigger", "hello_world"],
    )
    assert "queued" in output or "triggered" in output, (
        f"DAG trigger did not return 'queued'.\nOutput: {output}"
    )

    deadline = time.time() + E2E_TIMEOUT
    seen_pod = False

    while time.time() < deadline:
        time.sleep(5)
        task_pods = [
            p
            for p in k8s.list_namespaced_pod(namespace).items
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

    pytest.fail(
        f"hello_world did not complete within {E2E_TIMEOUT}s (pod seen: {seen_pod})"
    )


# ---------------------------------------------------------------------------
# Unit tests – no cluster required
# ---------------------------------------------------------------------------


def test_pod_template_has_kueue_queue_label() -> None:
    """The pod template must carry kueue.x-k8s.io/queue-name as a *label*
    (not an annotation) for Kueue's mutating webhook to add a scheduling gate."""
    with open("helm/pod_template.yaml") as f:
        tmpl = yaml.safe_load(f)
    labels = tmpl.get("metadata", {}).get("labels", {})
    assert "kueue.x-k8s.io/queue-name" in labels, (
        "kueue.x-k8s.io/queue-name must be a label on the pod template, not an annotation"
    )


def test_pod_template_has_no_kueue_managed_label() -> None:
    """Kueue sets kueue.x-k8s.io/managed itself; pre-setting it in the pod
    template causes the webhook to skip gate injection."""
    with open("helm/pod_template.yaml") as f:
        tmpl = yaml.safe_load(f)
    labels = tmpl.get("metadata", {}).get("labels", {})
    assert "kueue.x-k8s.io/managed" not in labels, (
        "kueue.x-k8s.io/managed must NOT be pre-set in the pod template"
    )


def test_kueue_resources_yaml_has_required_kinds() -> None:
    """kueue-resources.yaml must define a ResourceFlavor, a ClusterQueue and
    a LocalQueue so the install script applies a complete queue hierarchy."""
    with open("helm/kueue-resources.yaml") as f:
        docs = list(yaml.safe_load_all(f))
    kinds = {d["kind"] for d in docs if d}
    assert "ResourceFlavor" in kinds, "kueue-resources.yaml missing ResourceFlavor"
    assert "ClusterQueue" in kinds, "kueue-resources.yaml missing ClusterQueue"
    assert "LocalQueue" in kinds, "kueue-resources.yaml missing LocalQueue"


def test_kueue_values_uses_pod_framework() -> None:
    """helm/kueue-values.yaml must enable the 'pod' integration framework."""
    with open("helm/kueue-values.yaml") as f:
        vals = yaml.safe_load(f)
    cfg_yaml = vals["managerConfig"]["controllerManagerConfigYaml"]
    cfg = yaml.safe_load(cfg_yaml)
    frameworks = cfg.get("integrations", {}).get("frameworks", [])
    assert "pod" in frameworks, (
        "Kueue values must include 'pod' in integrations.frameworks"
    )


def test_kueue_memory_test_dag_has_queue_name_label() -> None:
    """The executor_config in the test DAG must set queue-name via pod labels,
    not annotations, to match what the pod template provides."""
    import ast, textwrap

    with open("dags/kueue_memory_test.py") as f:
        src = f.read()
    # Quick textual check: the label key must appear somewhere in the file
    assert "kueue.x-k8s.io/queue-name" in src, (
        "kueue_memory_test.py must reference kueue.x-k8s.io/queue-name"
    )


# ---------------------------------------------------------------------------
# Integration tests – require a live cluster
# ---------------------------------------------------------------------------

KUEUE_GATE = "kueue.x-k8s.io/admission"
KUEUE_E2E_TIMEOUT = 120  # seconds


def test_kueue_controller_is_running(k8s: CoreV1Api, kueue_namespace: str) -> None:
    pods = k8s.list_namespaced_pod(kueue_namespace).items
    controller_pods = [p for p in pods if "kueue-controller-manager" in p.metadata.name]
    assert controller_pods, f"No kueue-controller-manager pod in '{kueue_namespace}'"
    pod = controller_pods[0]
    ready = any(
        c.type == "Ready" and c.status == "True" for c in (pod.status.conditions or [])
    )
    assert ready, f"kueue-controller-manager pod is not Ready: {pod.metadata.name}"


def test_kueue_local_queue_exists(namespace: str) -> None:
    result = subprocess.run(
        ["kubectl", "get", "localqueue", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"kubectl get localqueue failed: {result.stderr}"
    queues = json.loads(result.stdout)["items"]
    assert queues, f"No LocalQueue found in namespace '{namespace}'"


def test_kueue_cluster_queue_exists() -> None:
    result = subprocess.run(
        ["kubectl", "get", "clusterqueue", "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"kubectl get clusterqueue failed: {result.stderr}"
    queues = json.loads(result.stdout)["items"]
    assert queues, "No ClusterQueue found in cluster"


def test_kueue_e2e_gates_second_pod(k8s: CoreV1Api, namespace: str, e2e: bool) -> None:
    """Create two pods that each request the full ClusterQueue memory quota.
    The first should be admitted immediately; the second must be SchedulingGated
    until the first completes.  Verifies Kueue is enforcing the quota end-to-end."""
    if not e2e:
        pytest.skip("--e2e not set")

    pod_names = ["kueue-e2e-test-a", "kueue-e2e-test-b"]
    labels = {"kueue.x-k8s.io/queue-name": "airflow"}
    ADMISSION_GATE = "kueue.x-k8s.io/admission"
    ADMISSION_TIMEOUT = 30

    print(f"\n[e2e] namespace={namespace}  pods={pod_names}")
    print(f"[e2e] ClusterQueue quota: 1Gi — expecting exactly 1 pod admitted, 1 gated")

    # --- cleanup -----------------------------------------------------------
    print("[e2e] Deleting leftover pods from previous runs (if any)...")
    for name in pod_names:
        try:
            k8s.delete_namespaced_pod(name, namespace)
            print(f"[e2e]   deleted {name}")
        except ApiException:
            pass

    print("[e2e] Waiting for pods to be fully removed...")
    deadline = time.time() + 60
    for name in pod_names:
        while time.time() < deadline:
            try:
                k8s.read_namespaced_pod(name, namespace)
                time.sleep(1)
            except ApiException as exc:
                if exc.status == 404:
                    print(f"[e2e]   {name} gone")
                    break
                raise

    # --- create pods -------------------------------------------------------
    print("[e2e] Creating test pods (each requests 1Gi memory)...")
    for name in pod_names:
        k8s.create_namespaced_pod(
            namespace,
            k8s_client.V1Pod(
                metadata=k8s_client.V1ObjectMeta(
                    name=name, namespace=namespace, labels=labels
                ),
                spec=k8s_client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        k8s_client.V1Container(
                            name="test",
                            image="busybox",
                            command=["sleep", "120"],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"memory": "1Gi", "cpu": "100m"},
                            ),
                        )
                    ],
                ),
            ),
        )
        print(f"[e2e]   created {name}")

    # --- poll for admission ------------------------------------------------
    # Both pods start with kueue.x-k8s.io/admission (quota gate) and possibly
    # kueue.x-k8s.io/topology (TAS gate) set.  Kueue removes the admission
    # gate from the pod it admits; the topology gate is a separate concern.
    print(
        f"[e2e] Polling for Kueue admission gate removal (timeout={ADMISSION_TIMEOUT}s)..."
    )
    deadline = time.time() + ADMISSION_TIMEOUT
    admission_gates: dict[str, bool] = {}
    iteration = 0
    while time.time() < deadline:
        time.sleep(2)
        iteration += 1
        pods = {name: k8s.read_namespaced_pod(name, namespace) for name in pod_names}
        admission_gates = {
            name: any(
                g.name == ADMISSION_GATE for g in (pod.spec.scheduling_gates or [])
            )
            for name, pod in pods.items()
        }
        gate_summary = ", ".join(
            f"{n}={'gated' if gated else 'admitted'}"
            for n, gated in admission_gates.items()
        )
        all_gates = {
            name: [g.name for g in (pod.spec.scheduling_gates or [])]
            for name, pod in pods.items()
        }
        print(f"[e2e]   poll #{iteration}: {gate_summary}  (all gates: {all_gates})")
        still_waiting = sum(admission_gates.values())
        if still_waiting == 1:
            print(f"[e2e] Target state reached after {iteration} polls.")
            break

    still_waiting = sum(admission_gates.values())
    admitted_count = len(pod_names) - still_waiting
    print(f"[e2e] Final: admitted={admitted_count} gated={still_waiting}")

    # Exactly one pod should have its admission gate removed (quota admitted),
    # the other should still hold the admission gate (queued, awaiting quota).
    assert admitted_count == 1, (
        f"Expected exactly 1 pod with admission gate removed, got {admitted_count}. "
        f"Admission gates still present: {admission_gates}"
    )
    assert still_waiting == 1, (
        f"Expected exactly 1 pod still holding admission gate, got {still_waiting}. "
        f"Admission gates still present: {admission_gates}"
    )

    # --- cleanup -----------------------------------------------------------
    print("[e2e] Test passed. Cleaning up pods...")
    for name in pod_names:
        try:
            k8s.delete_namespaced_pod(name, namespace)
        except ApiException:
            pass
