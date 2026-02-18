"""
sitecustomize.py — auto-connect Airflow task processes to the VS Code debugger.

How it works:
  Python imports sitecustomize at startup for every process. We guard with
  AIRFLOW_CTX_TASK_ID, which Airflow sets *only* inside task subprocess
  environments — so the main Celery worker process is never touched.

Activation:
  1. Start "Airflow: Debug Worker Tasks" in VS Code Run & Debug.
  2. Trigger a DAG run — every task subprocess auto-connects and your
     breakpoints are hit. No decorator or DAG code changes needed.

AIRFLOW_DEBUG=1 must be set on the worker (done in docker-compose.debug.yaml).
"""

import os
import socket


def _vscode_is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


if os.environ.get("AIRFLOW_DEBUG") == "1":
    pass  # sitecustomize does not work with Airflow 3 fork model — use @debuggable instead

if (
    os.environ.get("AIRFLOW_DEBUG") == "1"
    and os.environ.get("AIRFLOW_CTX_TASK_ID")
):
    _host = os.environ.get("DEBUGPY_HOST", "host.docker.internal")
    _port = int(os.environ.get("DEBUGPY_PORT", "5683"))

    if _vscode_is_listening(_host, _port):
        try:
            import debugpy

            if not debugpy.is_client_connected():
                debugpy.connect((_host, _port))
                debugpy.wait_for_client()
        except Exception:
            pass
