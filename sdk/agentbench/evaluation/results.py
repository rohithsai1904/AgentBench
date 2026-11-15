"""Result types: what an evaluation run produces.

RunResult
 └─ CaseResult (one per dataset case): the task's output, its trace id, and its scores
     └─ Score (one per evaluator)
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..tracing.span import to_jsonable


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------- Score
@dataclass(frozen=True)
class Score:
    """One evaluator's verdict on one case."""

    name: str                          # which evaluator, e.g. "exact_match"
    value: Optional[float]             # 0.0 .. 1.0, or None = "not scored" (skipped or errored)
    passed: Optional[bool] = None      # value >= the evaluator's threshold; None if not scored
    reason: str = ""                   # short human-readable explanation
    error: Optional[str] = None        # set only if the evaluator itself crashed
    metadata: dict = field(default_factory=dict)  # extras, e.g. a judge's raw reply

    def __post_init__(self) -> None:
        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise TypeError(f"Score.value must be a number or None, got {type(self.value).__name__}")
            if math.isnan(self.value) or not 0.0 <= self.value <= 1.0:
                raise ValueError(f"Score.value must be between 0 and 1, got {self.value}")

    @property
    def status(self) -> str:
        if self.error is not None:
            return "error"
        return "scored" if self.value is not None else "skipped"

    @classmethod
    def skipped(cls, name: str, reason: str) -> "Score":
        """Not applicable (e.g. the case has no expected answer). NOT the same as a score of 0."""
        return cls(name=name, value=None, reason=reason)

    @classmethod
    def errored(cls, name: str, error: BaseException | str) -> "Score":
        """The evaluator crashed. Recorded, so one bad evaluator never kills the run."""
        text = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
        return cls(name=name, value=None, error=text, reason="evaluator failed")

    def to_dict(self) -> dict:
        return {
            "name": self.name, "value": self.value, "passed": self.passed, "reason": self.reason,
            "error": self.error, "status": self.status, "metadata": to_jsonable(self.metadata),
        }


@dataclass
class CaseResult:
    """Everything that happened for one dataset case."""

    case_id: str
    output: Any = None
    scores: list[Score] = field(default_factory=list)
    error: Optional[str] = None
    trace_id: Optional[str] = None
    latency_ms: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def score_for(self, name: str) -> Optional[Score]:
        return next((s for s in self.scores if s.name == name), None)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id, "output": to_jsonable(self.output),
            "scores": [s.to_dict() for s in self.scores], "error": self.error,
            "trace_id": self.trace_id, "latency_ms": self.latency_ms,
        }


@dataclass
class RunResult:
    """One execution of one task over one dataset version."""

    dataset_name: str
    dataset_version: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    config: dict = field(default_factory=dict)   # what was tested, e.g. {"prompt": "v2"}
    started_at: datetime = field(default_factory=_now)
    ended_at: Optional[datetime] = None
    cases: list[CaseResult] = field(default_factory=list)

    def finish(self) -> None:
        self.ended_at = _now()

    @property
    def n_cases(self) -> int:
        return len(self.cases)

    @property
    def n_errors(self) -> int:
        return sum(1 for c in self.cases if not c.ok)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version, "config": to_jsonable(self.config),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "cases": [c.to_dict() for c in self.cases],
        }