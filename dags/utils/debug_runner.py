"""
Debugpy entry point for Airflow DAGs.

Usage: python -Xfrozen_modules=off dags/utils/debug_runner.py <dag_file.py>

Owns the full debugpy lifecycle. After wait_for_client() we mark every background
thread with BOTH is_pydev_daemon_thread AND pydev_do_not_trace.

Why both flags?
  is_pydev_daemon_thread — skips the thread in suspend_all_threads(), process_internal_commands()
  pydev_do_not_trace     — the ONLY flag checked inside trace_dispatch() itself
                           (pydevd calls threading.settrace(trace_dispatch) globally,
                            so every new thread gets the trace function automatically;
                            without this flag trace_dispatch runs on the thread and
                            may try to suspend it)

Why PYDEVD_USE_SYS_MONITORING=false?
  Python 3.12 defaults to sys.monitoring instead of sys.settrace for pydevd callbacks.
  In sys.monitoring mode, monitoring is per-code-object (global across threads),
  and the thread-level flags (pydev_do_not_trace) live in trace_dispatch_regular.py
  which is bypassed entirely.  Forcing sys.settrace restores the code path where
  our background-thread flags actually work.
"""

import os

# Must be set before `import debugpy` — pydevd_constants.py reads it at import time.
os.environ.setdefault("PYDEVD_USE_SYS_MONITORING", "false")
import sys
import threading
import runpy
import debugpy

PORT = int(os.environ.get("DEBUGPY_PORT", 5683))
debugpy.listen(("0.0.0.0", PORT))

# Signal VS Code's problemMatcher, then wait for the client to attach.
print("wait_for_client", file=sys.stderr, flush=True)
debugpy.wait_for_client()

_main = threading.current_thread()


def _mark_background_thread(t: threading.Thread) -> None:
    """Mark a non-main thread so pydevd ignores it completely."""
    t.is_pydev_daemon_thread = True  # type: ignore[attr-defined]  skips suspend / internal cmds
    t.pydev_do_not_trace = True  # type: ignore[attr-defined]  skips trace_dispatch


# Mark all currently-running background threads.
for _t in threading.enumerate():
    if _t is not _main:
        _mark_background_thread(_t)

# Patch Thread.start so every future background thread is also marked
# before its first Python instruction is executed.
_original_thread_start = threading.Thread.start


def _patched_thread_start(self, *args, **kwargs) -> None:  # type: ignore[override]
    _mark_background_thread(self)
    _original_thread_start(self, *args, **kwargs)


threading.Thread.start = _patched_thread_start  # type: ignore[method-assign]

dag_path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(dag_path)))
runpy.run_path(dag_path, run_name="__main__")
