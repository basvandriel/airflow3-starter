"""
Debugpy entry point for Airflow DAGs.

Usage:
    python -Xfrozen_modules=off dags/utils/debug_runner.py <dag_file.py>

This script is the programmatic alternative to running:
    python -m debugpy --listen ... --wait-for-client dag.py

It explicitly owns the full debugpy lifecycle:
    1. Set PYDEVD_USE_SYS_MONITORING=false  (must happen before any debugpy import)
    2. Call debugpy.listen() to open the debug port
    3. Print "wait_for_client" so the VS Code task problemMatcher can detect readiness
    4. Block on debugpy.wait_for_client() until VS Code attaches
    5. Mark all background threads so pydevd ignores them (see below)
    6. Run the DAG file via runpy so breakpoints work as if it were __main__

───────────────────────────────────────────────────────────────────────────────
THE PROBLEM: process hangs after the first breakpoint continue
───────────────────────────────────────────────────────────────────────────────
Airflow 3's dag.test() uses an InProcessTestSupervisor that runs each task's
code on the main thread.  For every task it also spins up a background thread
(_handle_socket_comms) which loops on selector.select(timeout=1.0) to ferry
stdout/stderr between the task and the supervisor.

When VS Code hits a breakpoint and then the user presses Continue, pydevd calls
suspend_all_threads(), which:
  - sets pydev_state = STATE_SUSPEND on every non-daemon thread it can find
  - calls restart_events() to reset the monitoring hooks

If _handle_socket_comms ends up with STATE_SUSPEND set, it blocks inside
_do_wait_suspend() waiting for a "resume" command from VS Code.  But VS Code
only sends one resume command (for the main thread).  The background thread
never gets its resume → deadlock → process hangs forever.

───────────────────────────────────────────────────────────────────────────────
WHY THE OBVIOUS FIXES DIDN'T WORK: Python 3.12 sys.monitoring
───────────────────────────────────────────────────────────────────────────────
pydevd has two completely separate tracing engines:

  sys.settrace path  (Python < 3.12):
    Each thread gets its own trace callback via threading.settrace().
    The callback is trace_dispatch_regular.py::trace_dispatch().
    Inside that function, the FIRST thing checked is:
        if getattr(thread, 'pydev_do_not_trace', False): return None
    Returning None disables tracing for that thread entirely.
    Additionally, suspend_all_threads() iterates threading.enumerate() and
    skips any thread where pydev_do_not_trace is set.

  sys.monitoring path  (Python 3.12+ DEFAULT, PEP 669):
    Monitoring hooks are registered per-code-object, GLOBALLY across all threads.
    When any thread executes a monitored code object, the callback fires —
    regardless of per-thread flags.
    trace_dispatch_regular.py is NEVER called in this mode.
    The active callbacks live in _pydevd_sys_monitoring/_pydevd_sys_monitoring.py.
    Although _create_thread_info() does check is_pydev_daemon_thread and returns
    ThreadInfo(trace=False), additional mechanisms — notably restart_events()
    which re-registers global sys.monitoring hooks after each suspension — can
    still cause background threads to receive LINE events and enter _do_wait_suspend.

Setting is_pydev_daemon_thread=True and pydev_do_not_trace=True on background
threads targets the sys.settrace path.  On Python 3.12 with sys.monitoring active
those flags have no reliable effect, so the hang persists.

───────────────────────────────────────────────────────────────────────────────
THE FIX: force sys.settrace by setting PYDEVD_USE_SYS_MONITORING=false
───────────────────────────────────────────────────────────────────────────────
pydevd_constants.py (line ~209) reads PYDEVD_USE_SYS_MONITORING at import time:

    PYDEVD_USE_SYS_MONITORING = IS_PY312_OR_GREATER and hasattr(sys, "monitoring")
    if PYDEVD_USE_SYS_MONITORING:
        _val = os.getenv("PYDEVD_USE_SYS_MONITORING", "").lower()
        if _val in ("no", "false", "0"):
            PYDEVD_USE_SYS_MONITORING = False

Setting it to "false" BEFORE any debugpy/pydevd import restores the sys.settrace
path on Python 3.12, where is_pydev_daemon_thread and pydev_do_not_trace work
exactly as intended.

───────────────────────────────────────────────────────────────────────────────
WHY BOTH THREAD FLAGS ARE STILL NEEDED (sys.settrace path)
───────────────────────────────────────────────────────────────────────────────
  is_pydev_daemon_thread = True
    pydevd patches threading.enumerate() to hide threads carrying this attribute.
    suspend_all_threads() iterates that patched enumerate() — so the background
    thread is never handed to mark_thread_suspended() and never gets STATE_SUSPEND.
    Also skips the thread in process_internal_commands().

  pydev_do_not_trace = True
    pydevd calls threading.settrace(trace_dispatch) globally, so every new thread
    automatically gets the trace function.  trace_dispatch_regular.py checks this
    flag first and returns None immediately, preventing any suspension logic from
    running even if the thread somehow bypasses enumerate().

Both flags together provide defence-in-depth: one prevents the thread from ever
being scheduled for suspension; the other prevents it from reacting even if it is.

───────────────────────────────────────────────────────────────────────────────
WHY Thread.start IS PATCHED
───────────────────────────────────────────────────────────────────────────────
The _handle_socket_comms thread is created by Airflow AFTER wait_for_client()
returns — i.e., after pydevd is already active.  We must mark the thread BEFORE
its first Python instruction executes; setting the attribute after start() is a
race condition.  Patching Thread.start() guarantees the flags are set on self
before _original_thread_start() hands control to the new thread.

The initial for-loop over threading.enumerate() handles threads already running
when this script starts (debugpy's own reader/writer threads).
"""

import os

# Must be set before `import debugpy` — pydevd_constants.py reads it at import time.
# Force-disable the PYDEVD sys.monitoring path so pydevd honors
# per-thread flags (required to avoid dag.test() deadlocks on Python 3.12+).
os.environ["PYDEVD_USE_SYS_MONITORING"] = "false"
import sys
import threading
import runpy
import debugpy

PORT = int(os.environ.get("DEBUGPY_PORT", 5683))
debugpy.listen(("0.0.0.0", PORT))

# Signal VS Code's problemMatcher, then wait for the client to attach.
# include port/pid to make readiness obvious in logs while preserving the
# exact `wait_for_client` token that the problemMatcher looks for.
print(f"wait_for_client port={PORT} pid={os.getpid()}", file=sys.stderr, flush=True)
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

# Basic argument validation so the script fails fast with a helpful message.`
if len(sys.argv) < 2:
    print("Usage: debug_runner.py <dag_file.py>", file=sys.stderr)
    sys.exit(2)

dag_path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(dag_path)))
try:
    runpy.run_path(dag_path, run_name="__main__")
except Exception:
    import traceback

    traceback.print_exc()
    sys.exit(1)
