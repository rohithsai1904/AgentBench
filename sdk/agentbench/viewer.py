from __future__ import annotations

from typing import Any, Optional


def _ms(duration_ms: Optional[float]) -> str:
    if duration_ms is None:
        return "?"
    return f"{duration_ms:.0f}ms"


def _span_line(node: dict[str, Any], depth: int) -> str:
    mark = "x" if node.get("status") == "error" else "-"
    err = ""
    if node.get("status") == "error":
        err = f"  !! {node.get('error_type')}: {node.get('error_message')}"
    orphan = "  (orphaned)" if node.get("orphaned") else ""
    return (
        f"{'  ' * depth}{mark} {node.get('name')} [{node.get('kind')}] "
        f"{_ms(node.get('duration_ms'))}{err}{orphan}"
    )


def format_trace(trace: dict[str, Any]) -> str:
    """Pretty-print a GET /v1/traces/{id} payload (nested `tree`)."""
    lines = [
        f"{trace.get('name')} [{trace.get('status')}] {_ms(trace.get('duration_ms'))}  id={trace.get('id')}"
    ]
    tree = trace.get("tree") or []
    if not tree:
        lines.append("  (no spans)")
        return "\n".join(lines)

    def walk(node: dict[str, Any], depth: int) -> None:
        lines.append(_span_line(node, depth))
        for child in node.get("children") or []:
            walk(child, depth + 1)

    for root in tree:
        walk(root, 0)
    return "\n".join(lines)


def print_trace(trace: dict[str, Any]) -> None:
    print(format_trace(trace))
