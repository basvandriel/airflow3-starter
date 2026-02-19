"""
Debugpy entry point for Airflow DAGs.

Usage: python -m debugpy --listen ... debug_runner.py <dag_file.py>

In attach/listen mode VS Code sets suspend_policy="ALL" on every breakpoint,
which freezes all threads including Airflow's supervisor IPC thread
(_handle_socket_comms). With that frozen the session hangs. Marking threads
with is_pydev_daemon_thread=True tells pydevd to exclude them from suspension.
We patch Thread.start so it applies automatically to every thread dag.test()
spawns, without touching DAG files or Airflow internals.
"""

import os
import sys
import threading
import runpy

_original_start = threading.Thread.start


def _patched_start(self: threading.Thread, *args, **kwargs) -> None:
    _original_start(self, *args, **kwargs)
    self.is_pydev_daemon_thread = True  # type: ignore[attr-defined]


threading.Thread.start = _patched_start  # type: ignore[method-assign]

dag_path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(dag_path)))
runpy.run_path(dag_path, run_name="__main__")
