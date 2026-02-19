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
    # pydevd/debugpy extension point: mark this thread so the debugger does not suspend it.
    self.is_pydev_daemon_thread = True  # type: ignore[attr-defined]


threading.Thread.start = _patched_start  # type: ignore[method-assign]

# Airflow's VariableAccessor and context objects may make live API/DB calls for ANY attribute
# access, including dunders like __iter__ that pydevd inspects at breakpoints.
# Raise AttributeError for dunder keys to prevent spurious errors and slowdowns.

# Patch VariableAccessor (context['var'])
try:
    from airflow.sdk.execution_time.context import VariableAccessor as _VariableAccessor
    _orig_variable_getattr = _VariableAccessor.__getattr__
    def _patched_variable_getattr(self: _VariableAccessor, key: str):  # type: ignore[override]
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError(key)
        return _orig_variable_getattr(self, key)
    _VariableAccessor.__getattr__ = _patched_variable_getattr  # type: ignore[method-assign]
except ImportError:
    pass

# Patch TaskInstance (context['ti']) if it has problematic __getattr__
try:
    from airflow.models.taskinstance import TaskInstance as _TaskInstance
    if hasattr(_TaskInstance, '__getattr__'):
        _orig_ti_getattr = _TaskInstance.__getattr__
        def _patched_ti_getattr(self: _TaskInstance, key: str):  # type: ignore[override]
            if key.startswith("__") and key.endswith("__"):
                raise AttributeError(key)
            return _orig_ti_getattr(self, key)
        _TaskInstance.__getattr__ = _patched_ti_getattr  # type: ignore[method-assign]
except (ImportError, AttributeError):
    pass

# Patch DagRun (context['dag_run']) if it has problematic __getattr__  
try:
    from airflow.models.dagrun import DagRun as _DagRun
    if hasattr(_DagRun, '__getattr__'):
        _orig_dagrun_getattr = _DagRun.__getattr__
        def _patched_dagrun_getattr(self: _DagRun, key: str):  # type: ignore[override]
            if key.startswith("__") and key.endswith("__"):
                raise AttributeError(key)
            return _orig_dagrun_getattr(self, key)
        _DagRun.__getattr__ = _patched_dagrun_getattr  # type: ignore[method-assign]
except (ImportError, AttributeError):
    pass

dag_path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(dag_path)))
runpy.run_path(dag_path, run_name="__main__")
