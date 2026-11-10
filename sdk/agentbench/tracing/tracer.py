from __future__ import annotations

import contextvars
import functools
import inspect
import logging
import threading
from typing import Any, Callable, Optional

from ..llm_info import extract_usage
from .span import Span, new_trace_id, to_jsonable

log = logging.getLogger("agentbench")

_current_span: contextvars.ContextVar[Optional[Span]] = contextvars.ContextVar(
    "agentbench_current_span", default=None
)

_lock = threading.Lock()
_open: dict[str, list[Span]] = {}   
finished_spans: list[Span] = []
_exporter: Optional[Callable[[Span, list[Span]], None]] = None  # called with (root, all spans)


def set_exporter(fn: Optional[Callable[[Span, list[Span]], None]]) -> None:
    global _exporter
    _exporter = fn


def current_span() -> Optional[Span]:
    return _current_span.get()


def clear() -> None:
    with _lock:
        finished_spans.clear()
        _open.clear()


def _finish_trace(root: Span, spans: list[Span]) -> None:
    exporter = _exporter
    if exporter is None:  # local mode: just keep them in memory
        with _lock:
            finished_spans.extend(spans)
        return
    try:
        exporter(root, spans)
    except Exception:
        log.warning("agentbench: failed to export trace %s", root.trace_id, exc_info=True)


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
            trace_id=parent.trace_id if parent else new_trace_id(),
            parent_span_id=parent.id if parent else None,
        )
        if parent is None:  # a new root: start collecting this trace's spans
            with _lock:
                _open[self.span.trace_id] = []
        self._token = _current_span.set(self.span)
        return self.span

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.span is not None and self._token is not None
        if exc is not None:
            self.span.record_exception(exc)
        self.span.end()
        _current_span.reset(self._token)

        finished_trace: Optional[list[Span]] = None
        with _lock:
            bucket = _open.get(self.span.trace_id)
            if bucket is None:
                return False  # a straggler finishing after its trace was already sent
            bucket.append(self.span)
            if self.span.parent_span_id is None:  # the root ended -> the trace is complete
                finished_trace = _open.pop(self.span.trace_id)
        if finished_trace is not None:
            _finish_trace(self.span, finished_trace)
        return False

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self.__exit__(exc_type, exc, tb)


def span(name: str, kind: str = "function") -> SpanScope:
    return SpanScope(name, kind)


def observe(_fn: Optional[Callable] = None, *, name: Optional[str] = None, kind: str = "function",_post=None):
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
        
        def record_output(s: Span, result: Any) -> None:
            s.output = to_jsonable(result)
            if _post is not None:
                try:
                    _post(s, result)
                except Exception:  # telemetry must never break the call
                    log.warning("agentbench: post-processing failed", exc_info=True)
        
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with span(span_name, kind) as s:
                    s.input = capture_input(args, kwargs)
                    result = await fn(*args, **kwargs)
                    record_output(s,result)
                    return result

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, kind) as s:
                s.input = capture_input(args, kwargs)
                result = fn(*args, **kwargs)
                record_output(s,result)
                return result

        return wrapper

    return decorator(_fn) if _fn is not None else decorator


def trace(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "agent")
    return observe(_fn, **kw)


def tool(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "tool")
    return observe(_fn, **kw)


def llm(_fn: Optional[Callable] = None, **kw: Any):
    kw.setdefault("kind", "llm")
    kw.setdefault("_post", _record_llm_usage)
    return observe(_fn, **kw)

def _record_llm_usage(span: Span, result: Any) -> None:
    span.attributes.update(extract_usage(result))

def wrap_context(fn: Callable) -> Callable:
    ctx = contextvars.copy_context()
    return lambda *a, **kw: ctx.run(fn, *a, **kw)