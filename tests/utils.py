from __future__ import annotations

import time
from typing import Optional

from kubernetes.client import CoreV1Api, V1Pod


def find_pod(k8s: CoreV1Api, namespace: str, name_prefix: str) -> Optional[V1Pod]:
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
    k8s: CoreV1Api, namespace: str, pod_name: str, timeout: int = 60
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
    from kubernetes.stream import stream

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
