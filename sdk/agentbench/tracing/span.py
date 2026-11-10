from __future__ import annotations

import secrets
import time
import traceback
import dataclasses
import math
from dataclasses import dataclass, field
from datetime import date,datetime, timedelta, timezone
from typing import Any, Optional


def new_trace_id() -> str:
    return secrets.token_hex(16) 


def new_span_id() -> str:
    return secrets.token_hex(8)  

def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[+{len(text) - limit} chars]"

def _safe_repr(value: Any, limit: int) -> str:
    try:
        return _cut(repr(value), limit)
    except Exception:  # even repr() can fail on broken objects
        return "<unserializable>"

def _convert(v: Any, max_str: int, max_items: int, max_depth: int, depth: int) -> Any:
    # 1. simple values pass through (strings are cut if too long)
    if v is None or isinstance(v, (bool, int)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else str(v)  # NaN / inf are not valid JSON
    if isinstance(v, str):
        return _cut(v, max_str)
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    
    # 2. stop going deeper (protects against huge or self-referencing structures)
    if depth >= max_depth:
        return _safe_repr(v, max_str)

    def rec(x: Any) -> Any:
        return _convert(x, max_str, max_items, max_depth, depth + 1)

    # 3. containers: convert each item, keep at most max_items
    if isinstance(v, dict):
        items = list(v.items())
        out = {str(k): rec(val) for k, val in items[:max_items]}
        if len(items) > max_items:
            out["..."] = f"{len(items) - max_items} more keys"
        return out
    
    if isinstance(v, (list, tuple, set, frozenset)):
        seq = list(v)
        out_list = [rec(x) for x in seq[:max_items]]
        if len(seq) > max_items:
            out_list.append(f"...{len(seq) - max_items} more items")
        return out_list
    
    # 4. objects: pydantic models (OpenAI / Anthropic responses) and dataclasses
    dump = getattr(v, "model_dump", None)
    if callable(dump):
        try:
            return rec(dump())
        except Exception:
            pass
        
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: rec(getattr(v, f.name, None)) for f in dataclasses.fields(v)}
    # 5. anything else
    return _safe_repr(v, max_str)


def to_jsonable(
    value: Any, *, max_str: int = 2000, max_items: int = 50, max_depth: int = 6
) -> Any:
    """Make any value JSON-safe and bounded in size. Never raises."""
    try:
        return _convert(value, max_str, max_items, max_depth, 0)
    except Exception:
        return _safe_repr(value, max_str)

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

def trace_payload(project_id: int, root: Span, spans: list[Span]) -> dict:
    """One finished trace, in the shape POST /v1/ingest expects."""
    return {
        "id": root.trace_id,
        "project_id": project_id,
        "name": root.name,
        "status": root.status,
        "input": root.input,
        "output": root.output,
        "start_time": root.start_time.isoformat(),
        "end_time": root.end_time.isoformat() if root.end_time else None,
        "duration_ms": root.duration_ms,
        "spans": [s.to_dict() for s in spans],
    }