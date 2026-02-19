# `dag.test()` hangs indefinitely when debugging with pydevd-based debuggers (VS Code, PyCharm)

## Summary

Debugging a DAG using `dag.test()` with VS Code (or any pydevd-based debugger) in attach mode causes the session to hang permanently as soon as a breakpoint is hit. The DAG appears to stop, the debugger shows it paused, but continuing never resumes execution and eventually the task times out.

## Environment

- Airflow 3.x
- Python 3.12
- debugpy 1.8.x / VS Code with Python extension (reproduces with PyCharm too — anything using pydevd)
- Triggered via `dag.test()` (e.g. `if __name__ == "__main__": dag.test()`)

## How to reproduce

1. Add `if __name__ == "__main__": dag.test()` to any DAG file.

2. Start debugpy in listen mode inside the Airflow worker container:
   ```bash
   python -Xfrozen_modules=off -m debugpy --listen 0.0.0.0:5678 --wait-for-client my_dag.py
   ```

3. Attach VS Code (or PyCharm) to port 5678.

4. Set a breakpoint anywhere inside a task function — e.g. the first line of a `PythonOperator` callable.

5. The breakpoint is hit and the debugger pauses correctly.

6. Press "Continue" (F5). Execution never resumes. The debugger stays in a paused state indefinitely until the task execution timeout is reached.

This does **not** reproduce when running `dag.test()` locally via VS Code's launch mode ("Python Debugger: Current File"). It only occurs in attach/listen mode.

## What's happening

When a breakpoint is hit in attach/listen mode, pydevd uses `suspend_policy="ALL"` — it freezes every thread in the process, not just the one that hit the breakpoint. This is normal behavior.

The problem is that `InProcessTestSupervisor._setup_subprocess_socket` spawns a `_handle_socket_comms` thread that handles active socket IPC between the supervisor and the task runner. When pydevd freezes it, the heartbeat/communication breaks down. The supervisor eventually considers the task dead and the session never recovers.

The `run_forever` asyncio thread has the same issue.

## Root cause

`_setup_subprocess_socket` in `supervisor.py`:

```python
thread = threading.Thread(target=self._handle_socket_comms, daemon=True)
```

pydevd provides `is_pydev_daemon_thread = True` as an explicit extension point for exactly this — it's how debugpy marks its own internal threads to exclude them from suspension. The `_handle_socket_comms` thread should be marked the same way.

Note: this does not reproduce in launch mode because VS Code uses Python 3.12's `sys.monitoring` API there, which handles per-thread breakpoints natively and never sets `suspend_policy="ALL"`. In attach mode it falls back to `sys.settrace` with all-thread suspension.

## Proposed fix

In `InProcessTestSupervisor._setup_subprocess_socket`, before `thread.start()`:

```python
thread = threading.Thread(target=self._handle_socket_comms, daemon=True)
thread.is_pydev_daemon_thread = True  # exclude from debugpy/pydevd thread suspension
```

Same for the `run_forever` thread if spawned in the same context.

`InProcessTestSupervisor` is specifically designed for development/test workflows — debugging is a primary use case — so this feels like the right layer to fix it rather than putting the workaround on every user.

## Workaround

Patch `threading.Thread.start` before calling `dag.test()` to auto-mark all spawned threads:

```python
_orig = threading.Thread.start
def _patched(self, *args, **kwargs):
    _orig(self, *args, **kwargs)
    self.is_pydev_daemon_thread = True
threading.Thread.start = _patched
dag.test()
```
