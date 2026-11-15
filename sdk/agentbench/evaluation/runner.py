"""Steps 5-7: run cases through the task, score them, and survive failures."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional, Sequence

from ..tracing import span, to_jsonable
from .evaluator.evaluator import Evaluator
from .results import CaseResult, RunResult, Score
from .evaluator.tasks import run_task

if TYPE_CHECKING:
    from agentbench.datasets import Record

log = logging.getLogger("agentbench")


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- step 7
async def _score_one(
    evaluator: Evaluator, case: "Record", output: Any, timeout: Optional[float]
) -> Score:
    """Run ONE evaluator, fully isolated: whatever happens, a Score comes back."""
    try:
        score = await asyncio.wait_for(evaluator.score(case, output), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        after = f" after {timeout}s" if timeout else ""
        return Score.errored(evaluator.name, f"timed out{after}")
    except Exception as exc:  # a crashing evaluator must not hurt the others
        return Score.errored(evaluator.name, exc)
    if not isinstance(score, Score):
        return Score.errored(
            evaluator.name, f"evaluator returned {type(score).__name__}, expected a Score"
        )
    return score


async def run_case(
    case: "Record",
    task: Callable[[dict], Any],
    evaluators: Sequence[Evaluator],
    *,
    timeout: float = 60,
    evaluator_timeout: Optional[float] = 120,
    run_id: Optional[str] = None,
) -> CaseResult:
    """Run one case: call the task, then score the output. Never raises for task/evaluator failures."""
    # The case gets its own root span, so every case is its own trace you can open later.
    # run_task copies the context, so everything the task does nests under this span.
    with span("eval_case", kind="agent") as s:
        s.input = to_jsonable(case.inputs)
        s.attributes["case_id"] = case.id
        
        if run_id:
            s.attributes["run_id"] = run_id  # lets you find every trace of one run

        result = CaseResult(case_id=case.id, trace_id=s.trace_id)

        started = time.perf_counter()
        try:
            result.output = await run_task(task, case.inputs, timeout=timeout)
        except Exception as exc:  # the task crashed or timed out: record it, don't raise
            result.error = _describe(exc)
            s.record_exception(exc)  # keeps the trace red, with the stack trace
        result.latency_ms = (time.perf_counter() - started) * 1000

        if result.error is not None:
            # Nothing to judge. Mark every evaluator "skipped" so each case still has one
            # score per evaluator, and the failure is counted through CaseResult.error.
            result.scores = [Score.skipped(ev.name, "task failed") for ev in evaluators]
            return result

        s.output = to_jsonable(result.output)
        for evaluator in evaluators:
            result.scores.append(await _score_one(evaluator, case, result.output, evaluator_timeout))
        return result


async def run_dataset(
    dataset: Iterable["Record"],
    task: Callable[[dict], Any],
    evaluators: Sequence[Evaluator],
    *,
    concurrency: int = 8,
    timeout: float = 60,
    evaluator_timeout: Optional[float] = 120,
    config: Optional[dict] = None,
    on_case_done: Optional[Callable[[CaseResult], None]] = None,
) -> RunResult:
    """Run every case, up to `concurrency` at a time, and return one RunResult.

    Results are in dataset order (not finishing order). Each call gets a new run_id.
    """
    evaluators = list(evaluators)
    names = [e.name for e in evaluators]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate evaluator names: {names}; give each one a unique name=...")
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    cases = list(dataset)

    run = RunResult(
        dataset_name=getattr(dataset, "name", "unnamed"),
        dataset_version=getattr(dataset, "version", ""),
        config={"evaluators": names, "concurrency": concurrency, "timeout": timeout, **(config or {})},
    )
    # The semaphore is a turnstile: only `concurrency` cases may be inside at once.
    # Real LLM APIs rate-limit you, so you need this limit.
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(case: "Record") -> CaseResult:
        async with semaphore:
            try:
                result = await run_case(
                    case, task, evaluators, timeout=timeout,
                    evaluator_timeout=evaluator_timeout, run_id=run.run_id,
                )
            except Exception as exc:  # a bug in the runner itself: record it, keep the run alive
                result = CaseResult(case_id=getattr(case, "id", "?"), error=f"runner error: {_describe(exc)}")
            if on_case_done is not None:
                try:
                    on_case_done(result)
                except Exception:  # a broken progress callback must not break the run
                    log.warning("agentbench: on_case_done callback failed", exc_info=True)
            return result

    # gather returns results in the order the coroutines were passed in,
    # even though they finish in a different order.
    run.cases = list(await asyncio.gather(*(guarded(c) for c in cases)))
    run.finish()
    return run