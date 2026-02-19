"""
Debugpy entry point for Airflow DAGs.

Usage: python -m debugpy --listen ... debug_runner.py <dag_file.py>

Root cause: in attach/listen mode VS Code's DAP initialize handshake sets
multi_threads_single_notification=True on the pydevd instance. This causes
every breakpoint's suspend_policy to be "ALL", which freezes ALL threads —
including Airflow's supervisor IPC thread (_handle_socket_comms). With that
thread frozen, the task runner heartbeat breaks and the session hangs.

In launch mode (local "Python Debugger: Current File") VS Code doesn't set
this flag, so suspend_policy stays "NONE" and only the hitting thread pauses.

Fix: set multi_threads_single_notification=False after pydevd initializes.
"""

import os
import sys
import runpy

try:
    import pydevd

    _pydb = pydevd.GetGlobalDebugger()
    if _pydb is not None:
        # Already initialized (unusual but handle it)
        _pydb.whymulti_threads_single_notification = False
    else:
        # Debugger not yet active — install a one-shot trace hook that fires
        # on the first line event after configurationDone, then removes itself.
        import threading

        def _fix_suspend_policy(frame, event, arg):
            try:
                _db = pydevd.GetGlobalDebugger()
                if _db is not None:
                    _db.multi_threads_single_notification = False
            except Exception:
                pass
            sys.settrace(None)
            threading.settrace(None)  # type: ignore[arg-type]
            return None

        sys.settrace(_fix_suspend_policy)
        threading.settrace(_fix_suspend_policy)  # type: ignore[arg-type]
except ImportError:
    pass

dag_path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(dag_path)))
runpy.run_path(dag_path, run_name="__main__")
