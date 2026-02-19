"""
Debug runner for Airflow DAGs using dag.test().

Usage (via tasks.json):
    python -m debugpy --listen 0.0.0.0:5683 --wait-for-client
        /opt/airflow/dags/utils/debug_runner.py /opt/airflow/dags/my_dag.py

Why this exists:
    When pydevd hits a breakpoint it calls suspend_all_threads(), which also
    freezes Airflow's internal background threads (_handle_socket_comms,
    run_forever). Those threads handle supervisor IPC; suspending them causes
    the debug session to hang permanently.

    The fix is to mark every non-MainThread as a pydevd daemon thread
    (is_pydev_daemon_thread=True) so pydevd skips them in suspend_all_threads().
    See: debugpy/_vendored/pydevd/_pydevd_bundle/pydevd_utils.py line 140.

    We do this by patching threading.Thread.start before dag.test() spins up
    those threads, which keeps this logic out of the DAG files themselves.
"""

import sys
import os
import threading
import runpy

# Patch threading.Thread.start so every thread spawned by dag.test() (e.g.
# _handle_socket_comms, run_forever) is marked as a pydevd daemon thread.
# MainThread is started by the interpreter, not Thread.start, so it is
# unaffected and will still hit breakpoints as normal.
_original_start = threading.Thread.start


def _patched_start(self: threading.Thread, *args, **kwargs) -> None:
    _original_start(self, *args, **kwargs)
    self.is_pydev_daemon_thread = True  # type: ignore[attr-defined]


threading.Thread.start = _patched_start  # type: ignore[method-assign]

# Run the DAG file passed as the first argument with __name__ == "__main__"
# so its `if __name__ == "__main__": dag.test()` block executes.
# Add the DAG file's directory to sys.path so relative imports (e.g. `from
# utils.download_utils import ...`) resolve the same way as running directly.
dag_path = sys.argv[1]
dag_dir = os.path.dirname(os.path.abspath(dag_path))
if dag_dir not in sys.path:
    sys.path.insert(0, dag_dir)
runpy.run_path(dag_path, run_name="__main__")
