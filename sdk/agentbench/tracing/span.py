from __future__ import annotations

import json
import secrets
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def new_trace_id() -> str:
    return secrets.token_hex(16) 


def new_span_id() -> str:
    return secrets.token_hex(8)  


def to_jsonable(value: Any) -> Any:
    """Make any value JSON-safe. Unknown objects become their repr(); never raises."""
    try:
        return json.loads(json.dumps(value, default=repr))
    except Exception:
        return repr(value)


@dataclass
class Span:
    name: str
    trace_id: str
    parent_span_id: Optional[str] = None
    kind: str = "function"  # agent | tool | llm | function
    id: str = field(default_factory=new_span_id)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str = "ok"  # ok | error
    input: Any = None
    output: Any = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_stacktrace: Optional[str] = None
    attributes: dict = field(default_factory=dict)  # default_factory: NOT a shared {}
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def end(self) -> None:
        if self.end_time is not None:  # calling twice is a no-op
            return
        self.duration_ms = (time.perf_counter() - self._t0) * 1000
        self.end_time = self.start_time + timedelta(milliseconds=self.duration_ms)

    def record_exception(self, exc: BaseException) -> None:
        self.status = "error"
        self.error_type = type(exc).__name__
        self.error_message = str(exc)
        self.error_stacktrace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "error_stacktrace": self.error_stacktrace,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
        }


def format_tree(spans: list[Span]) -> str:
    """Flat list of spans -> indented tree text (one tree per trace root)."""
    children: dict[Optional[str], list[Span]] = {}
    ids = {s.id for s in spans}
    for s in sorted(spans, key=lambda s: s.start_time):
        # a span whose parent isn't in the list is shown as a root
        key = s.parent_span_id if s.parent_span_id in ids else None
        children.setdefault(key, []).append(s)

    lines: list[str] = []

    def walk(span: Span, depth: int) -> None:
        mark = "x" if span.status == "error" else "-"
        ms = f"{span.duration_ms:.0f}ms" if span.duration_ms is not None else "?"
        err = f"  !! {span.error_type}: {span.error_message}" if span.status == "error" else ""
        lines.append(f"{'  ' * depth}{mark} {span.name} [{span.kind}] {ms}{err}")
        for child in children.get(span.id, []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)
    return "\n".join(lines)


def print_tree(spans: list[Span]) -> None:
    print(format_tree(spans))