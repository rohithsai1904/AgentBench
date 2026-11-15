from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, Optional


class TaskTimeoutError(Exception):
    """The task did not finish within its time limit."""


def _is_async(task: Callable) -> bool:
    while isinstance(task, functools.partial):  # partial(async_fn, ...) is still async
        task = task.func
    return inspect.iscoroutinefunction(task) or inspect.iscoroutinefunction(
        getattr(task, "__call__", None)  # an object with `async def __call__`
    )


async def _call(task: Callable, inputs: dict) -> Any:
    if _is_async(task):
        return await task(inputs)
    # A normal function would block the event loop and stop other cases running at the
    # same time, so run it in a worker thread. to_thread copies the current context, so
    # trace spans created inside still nest under the caller's span.
    result = await asyncio.to_thread(task, inputs)
    if inspect.isawaitable(result):  # a plain function that returned a coroutine
        result = await result
    return result


async def run_task(task: Callable[[dict], Any], inputs: dict, *, timeout: Optional[float] = None) -> Any:
    """Call task(inputs) and return its output.

    * `task` may be sync or async.
    * Exceptions raised by the task propagate unchanged (the runner records them).
    * If `timeout` (seconds) passes, the task is cancelled and TaskTimeoutError is raised.
      A sync task cannot be killed mid-run: its thread finishes in the background and the
      result is ignored.
    """
    if not callable(task):
        raise TypeError(f"task must be callable, got {type(task).__name__}")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive")

    work = asyncio.ensure_future(_call(task, inputs))  # own Task = own copy of the context
    try:
        done, _ = await asyncio.wait({work}, timeout=timeout)  # timeout=None waits forever
        if not done:
            work.cancel()
            await asyncio.wait({work})  # let the cancellation finish
            if not work.cancelled():
                work.exception()  # mark as retrieved so asyncio doesn't log a warning
            raise TaskTimeoutError(f"task did not finish within {timeout}s")
        return work.result()  # returns the output, or re-raises the task's own exception
    finally:
        if not work.done():  # e.g. we were cancelled from outside while waiting
            work.cancel()