"""
Debugpy entry point for Airflow DAGs.

Usage: python -m debugpy --listen ... debug_runner.py <dag_file.py>

Airflow 3's dag.test() runs tasks in-process, spawning background threads
(_handle_socket_comms, run_forever) for supervisor IPC. pydevd freezes ALL
threads on a breakpoint hit — including those IPC threads — causing the
session to hang. Marking them with is_pydev_daemon_thread=True tells pydevd
to skip them. We patch Thread.start so it applies to every thread dag.test()
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
