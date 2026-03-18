import json
import time

import pytest
from kubernetes import client as k8s_client
from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException

from tests.utils import exec_in_pod


def test_e2e_hello_world(
    k8s: CoreV1Api, namespace: str, chart_name: str, e2e: bool
) -> None:
    if not e2e:
        pytest.skip("--e2e not set")

    api_pod = next(
        p
        for p in k8s.list_namespaced_pod(namespace).items
        if p.metadata.name.startswith(f"{chart_name}-api-server")
    )

    output = exec_in_pod(
        k8s,
        namespace,
        api_pod.metadata.name,
        container="api-server",
        command=["airflow", "dags", "trigger", "hello_world"],
    )
    assert "queued" in output or "triggered" in output, (
        f"DAG trigger did not return expected output:\n{output}"
    )

    # Poll DAG run state — works with any executor (LocalExecutor, KubernetesExecutor).
    # We don't look for pods because LocalExecutor runs tasks inside the scheduler.
    deadline = time.time() + 300
    last_raw = ""

    while time.time() < deadline:
        time.sleep(5)
        raw = exec_in_pod(
            k8s,
            namespace,
            api_pod.metadata.name,
            container="api-server",
            command=["airflow", "dags", "list-runs", "-d", "hello_world", "-o", "json"],
        )
        last_raw = raw

        # The CLI may emit WARN/INFO lines before the JSON array; find the last `[`. 
        bracket = raw.rfind("[")
        if bracket == -1:
            continue
        try:
            runs = json.loads(raw[bracket:])
        except json.JSONDecodeError:
            continue

        # Log run states so we can diagnose timeouts.
        states = [run.get("state", "<unknown>") for run in runs]
        print(f"[e2e] hello_world runs: {states}")

        for run in runs:
            state = run.get("state", "")
            if state == "success":
                return
            if state in ("failed", "upstream_failed"):
                pytest.fail(f"hello_world DAG run ended in state '{state}'")

    pytest.fail(
        "hello_world did not reach state 'success' within 300s. "
        f"Last list-runs output:\n{last_raw}"
    )
def test_kueue_e2e_gates_second_pod(k8s: CoreV1Api, namespace: str, e2e: bool) -> None:
    if not e2e:
        pytest.skip("--e2e not set")

    pod_names = ["kueue-e2e-test-a", "kueue-e2e-test-b"]
    labels = {"kueue.x-k8s.io/queue-name": "airflow"}
    ADMISSION_GATE = "kueue.x-k8s.io/admission"

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
    print("[e2e] Polling for Kueue admission gate removal (timeout=30s)...")
    deadline = time.time() + 30
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

    assert admitted_count == 1
    assert still_waiting == 1

    # --- cleanup -----------------------------------------------------------
    print("[e2e] Test passed. Cleaning up pods...")
    for name in pod_names:
        try:
            k8s.delete_namespaced_pod(name, namespace)
        except ApiException:
            pass
