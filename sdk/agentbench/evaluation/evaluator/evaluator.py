from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Optional

from ..results import Score

if TYPE_CHECKING:
    from agentbench.datasets import Record


class Evaluator(ABC):

    name: str = ""  # subclasses set this; it is the registry key and the Score.name

    def __init__(self, *, name: Optional[str] = None, threshold: float = 0.5) -> None:
        self.name = name or type(self).name
        if not self.name:
            raise TypeError(f"{type(self).__name__} needs a class attribute `name` (or pass name=...)")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be between 0 and 1, got {threshold}")
        self.threshold = threshold

    @abstractmethod
    async def score(self, case: "Record", output: Any) -> Score:
        """Judge one output. Build the return value with self.result() or self.skipped()."""

    def result(self, value: float, reason: str = "", **metadata: Any) -> Score:
        """A scored result. `passed` is set for you: value >= threshold."""
        scored = Score(self.name, value, reason=reason, metadata=metadata)  # validates value
        return replace(scored, passed=scored.value >= self.threshold)

    def skipped(self, reason: str) -> Score:
        """Not applicable (e.g. the case has no expected answer). NOT the same as 0."""
        return Score.skipped(self.name, reason)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, threshold={self.threshold})"