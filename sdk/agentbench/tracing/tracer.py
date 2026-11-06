from __future__ import annotations

import contextvars
import functools
import inspect
import threading
from typing import Any, Callable, Optional

from span import Span, new_trace_id, to_jsonable

# "The span currently running in THIS thread / asyncio task".
_current_span: contextvars.ContextVar[Optional[Span]] = contextvars.ContextVar(
    "agentbench_current_span", default=None
)

# Finished spans are collected here (Day 5 will send them to the server instead).
finished_spans: list[Span] = []
_lock = threading.Lock()


def current_span() -> Optional[Span]:
    return _current_span.get()


def clear() -> None:
    with _lock:
        finished_spans.clear()


class SpanScope:
    """Context manager: `with span("x"):` and `async with span("x"):`"""

    def __init__(self, name: str, kind: str = "function") -> None:
        self.name = name
        self.kind = kind
        self.span: Optional[Span] = None
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> Span:
        parent = _current_span.get()
        self.span = Span(
            name=self.name,
            kind=self.kind,
            trace_id=parent.trace_id if parent else new_trace_id(),  # no parent -> new trace
            parent_span_id=parent.id if parent else None,
        )
        self._token = _current_span.set(self.span)  # I am now "current"
        return self.span

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.span is not None and self._token is not None
        if exc is not None:  # also catches CancelledError (it's a BaseException)
            self.span.record_exception(exc)
        self.span.end()
        _current_span.reset(self._token)  # restore the parent as current
        with _lock:
            finished_spans.append(self.span)
        return False  # never swallow the caller's exception

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self.__exit__(exc_type, exc, tb)


def span(name: str, kind: str = "function") -> SpanScope:
    return SpanScope(name, kind)


def observe(_fn: Optional[Callable] = None, *, name: Optional[str] = None, kind: str = "function"):
    """Decorator for sync and async functions. Works as @observe and @observe(name=...)."""

    def decorator(fn: Callable) -> Callable:
        span_name = name or fn.__name__
        sig = inspect.signature(fn)

        def capture_input(args: tuple, kwargs: dict) -> Any:
            try:
                bound = sig.bind_partial(*args, **kwargs).arguments
                data = {k: v for k, v in bound.items() if k not in ("self", "cls")}
            except TypeError:
                data = {"args": args, "kwargs": kwargs}
            return to_jsonable(data)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with span(span_name, kind) as s:
                    s.input = capture_input(args, kwargs)
                    result = await fn(*args, **kwargs)
                    s.output = to_jsonable(result)
                    return result

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, kind) as s:
                s.input = capture_input(args, kwargs)
                result = fn(*args, **kwargs)
                s.output = to_jsonable(result)
                return result

        return wrapper

    # used as @observe (no parentheses) -> _fn is the function; as @observe(...) -> _fn is None
    return decorator(_fn) if _fn is not None else decorator


def trace(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "agent")
    return observe(_fn, **kw)


def tool(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "tool")
    return observe(_fn, **kw)


def llm(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "llm")
    return observe(_fn, **kw)


def wrap_context(fn: Callable) -> Callable:
    """Threads do NOT inherit the current span. Wrap the function you hand to a thread."""
    ctx = contextvars.copy_context()
    return lambda *a, **kw: ctx.run(fn, *a, **kw)