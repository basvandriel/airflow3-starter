"""
Debug utilities for attaching VS Code / debugpy to Airflow task callables.

** Reverse-connect model **
VS Code listens as a server (launch.json "listen" mode); each task process calls
debugpy.connect() to reach it.  The VS Code session stays alive across all task
runs — you only start the debugger once.

Usage inside any PythonOperator callable:

    from utils.debug_utils import attach_debugpy

    def my_task(**context):
        attach_debugpy()   # connects to VS Code (only when AIRFLOW_DEBUG=1)
        ...

Or wrap a callable with the decorator:

    from utils.debug_utils import debuggable

    @debuggable
    def my_task(**context):
        ...

To activate:
  1. Start "Airflow: Debug Worker Tasks" in VS Code Run & Debug — VS Code
     starts listening on port 5683.
  2. Start the stack:  docker compose -f docker-compose.yaml -f docker-compose.debug.yaml up -d
  3. Trigger a DAG run.  Every task that calls attach_debugpy() will connect to
     the waiting VS Code session and hit your breakpoints.

AIRFLOW_DEBUG=1 must be set on the worker service (done in docker-compose.debug.yaml).
In normal runs the helper is a complete no-op with zero overhead.
"""

from __future__ import annotations

import functools
import os
from typing import Callable

# VS Code host as seen from inside the Docker container.
_VSCODE_HOST = os.environ.get("DEBUGPY_HOST", "host.docker.internal")


def _vscode_is_listening(
    host: str, port: int, retries: int = 20, delay: float = 0.5
) -> bool:
    import socket
    import time

    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(delay)
    return False


def attach_debugpy(port: int = 5683) -> None:
    if os.environ.get("AIRFLOW_DEBUG") != "1":
        return
    if not _vscode_is_listening(_VSCODE_HOST, port):
        return  # VS Code not listening — skip without importing debugpy
    try:
        import debugpy  # noqa: PLC0415 — intentional lazy import

        if not debugpy.is_client_connected():
            debugpy.connect((_VSCODE_HOST, port))
            debugpy.debug_this_thread()
            debugpy.wait_for_client()  # wait until VS Code finishes sending breakpoint config
        else:
            debugpy.debug_this_thread()
    except Exception:
        pass  # never let debugpy errors affect task execution


def debuggable(fn: Callable | None = None, *, port: int = 5683) -> Callable:
    """Decorator that calls attach_debugpy() before the wrapped task callable.

    Usage:
        @debuggable
        def my_task(**context): ...

        @debuggable(port=5684)
        def my_other_task(**context): ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attach_debugpy(port=port)
            return func(*args, **kwargs)

        return wrapper

    if fn is not None:
        # Called as @debuggable (no parentheses)
        return decorator(fn)
    # Called as @debuggable(...) with arguments
    return decorator
