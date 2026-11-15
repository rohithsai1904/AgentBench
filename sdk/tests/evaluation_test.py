import asyncio
import contextvars
import functools
import threading
import time

import pytest

from agentbench.evaluation import (
    Evaluator, Score, TaskTimeoutError, UnknownEvaluatorError, build_evaluators,
    get_evaluator, list_evaluators, register, run_task,
)
from agentbench.evaluation import registry
from agentbench.datasets import Record

CASE = Record("c1", {"message": "hi"}, {"answer": "hello"})


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Each test gets its own copy of the registry, so tests can't affect each other."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))


class Half(Evaluator):
    name = "half"

    async def score(self, case, output):
        return self.result(0.5, "always half")


# =============================================================== step 2: the interface
def test_evaluator_itself_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Evaluator()


def test_subclass_without_score_cannot_be_instantiated():
    class NoScore(Evaluator):
        name = "x"

    with pytest.raises(TypeError):
        NoScore()


def test_subclass_without_a_name_is_refused():
    class Nameless(Evaluator):
        async def score(self, case, output):
            return self.result(1.0)

    with pytest.raises(TypeError, match="name"):
        Nameless()
    assert Nameless(name="given").name == "given"


def test_score_is_awaitable_and_returns_a_score():
    s = asyncio.run(Half().score(CASE, "anything"))
    assert isinstance(s, Score) and s.name == "half" and s.value == 0.5 and s.reason == "always half"


def test_passed_comes_from_the_threshold_and_equal_counts_as_passing():
    assert Half(threshold=0.5).result(0.5).passed is True       # value >= threshold
    assert Half(threshold=0.5).result(0.49).passed is False
    assert Half(threshold=0.9).result(0.8).passed is False


def test_result_rejects_bad_values_and_threshold_is_validated():
    with pytest.raises(ValueError):
        Half().result(85)            # a percentage by mistake
    with pytest.raises(TypeError):
        Half().result("high")
    with pytest.raises(ValueError):
        Half(threshold=1.5)


def test_skipped_is_not_a_zero():
    s = Half().skipped("no expected answer")
    assert s.status == "skipped" and s.value is None and s.passed is None


def test_extra_metadata_is_kept_on_the_score():
    assert Half().result(1.0, "ok", judge_reply="yes").metadata == {"judge_reply": "yes"}


def test_subclass_with_its_own_options():
    class Length(Evaluator):
        name = "length"

        def __init__(self, max_words=3, **kw):
            super().__init__(**kw)
            self.max_words = max_words

        async def score(self, case, output):
            ok = len(str(output).split()) <= self.max_words
            return self.result(1.0 if ok else 0.0)

    ev = Length(max_words=2, threshold=1.0)
    assert asyncio.run(ev.score(CASE, "one two")).passed is True
    assert asyncio.run(ev.score(CASE, "one two three")).passed is False


# ================================================================ step 3: the registry
def test_register_sets_the_name_and_get_evaluator_builds_it_with_options():
    @register("my_metric")
    class M(Evaluator):
        def __init__(self, strict=False, **kw):
            super().__init__(**kw)
            self.strict = strict

        async def score(self, case, output):
            return self.result(1.0)

    ev = get_evaluator("my_metric", strict=True, threshold=0.7)
    assert isinstance(ev, M) and ev.name == "my_metric" and ev.strict and ev.threshold == 0.7
    assert "my_metric" in list_evaluators()


def test_unknown_name_gives_a_helpful_error():
    register("exact_match")(type("E", (Half,), {}))
    with pytest.raises(UnknownEvaluatorError) as e:
        get_evaluator("exact_mach")
    assert "Did you mean 'exact_match'" in str(e.value) and "Available" in str(e.value)


def test_duplicate_name_is_refused_but_registering_the_same_class_again_is_fine():
    @register("dup")
    class A(Half):
        pass

    register("dup")(A)  # same class again (e.g. a module imported twice): allowed
    with pytest.raises(ValueError, match="already taken"):
        @register("dup")
        class B(Half):
            pass

def test_register_refuses_things_that_are_not_evaluators():
    with pytest.raises(TypeError):
        register("bad")(dict)


def test_a_misspelled_option_names_the_evaluator():
    register("half")(Half)
    with pytest.raises(TypeError, match="evaluator 'half'"):
        get_evaluator("half", thresold=0.5)


def test_build_evaluators_accepts_names_dicts_and_instances():
    register("half")(Half)
    config = ["half", {"type": "half", "name": "half_strict", "threshold": 0.9}, Half(name="mine")]
    built = build_evaluators(config)
    assert [e.name for e in built] == ["half", "half_strict", "mine"]
    assert built[1].threshold == 0.9
    assert config[1] == {"type": "half", "name": "half_strict", "threshold": 0.9}  # input untouched


def test_build_evaluators_refuses_ambiguous_or_invalid_specs():
    register("half")(Half)
    with pytest.raises(ValueError, match="duplicate"):
        build_evaluators(["half", "half"])
    with pytest.raises(ValueError, match="type"):
        build_evaluators([{"threshold": 0.5}])
    with pytest.raises(TypeError):
        build_evaluators([42])


# ============================================================== step 4: the task wrapper
def test_async_and_sync_tasks_both_work():
    async def a(inputs):
        return inputs["x"] + 1

    def s(inputs):
        return inputs["x"] + 2

    assert asyncio.run(run_task(a, {"x": 1})) == 2
    assert asyncio.run(run_task(s, {"x": 1})) == 3


def test_sync_tasks_run_in_threads_and_do_not_block_each_other():
    caller = threading.get_ident()
    seen = []

    def slow(inputs):
        seen.append(threading.get_ident())
        time.sleep(0.15)
        return inputs["n"]

    async def main():
        t0 = time.perf_counter()
        out = await asyncio.gather(*[run_task(slow, {"n": i}) for i in range(4)])
        return out, time.perf_counter() - t0

    out, elapsed = asyncio.run(main())
    assert out == [0, 1, 2, 3]
    assert elapsed < 0.4              # run one after another it would take 4 x 0.15 = 0.6s
    assert caller not in seen         # the event loop thread itself was never blocked


def test_other_kinds_of_callables_are_recognised_as_async():
    async def base(inputs, extra=0):
        return inputs["x"] + extra

    class Callable_:
        async def __call__(self, inputs):
            return inputs["x"] * 10

    class Holder:
        async def method(self, inputs):
            return inputs["x"] * 100

    assert asyncio.run(run_task(functools.partial(base, extra=5), {"x": 1})) == 6
    assert asyncio.run(run_task(Callable_(), {"x": 1})) == 10
    assert asyncio.run(run_task(Holder().method, {"x": 1})) == 100


def test_a_plain_function_that_returns_a_coroutine_is_awaited():
    async def inner(inputs):
        return "done"

    assert asyncio.run(run_task(lambda inputs: inner(inputs), {})) == "done"


def test_the_tasks_own_exceptions_propagate_unchanged():
    def boom(inputs):
        raise KeyError("A-9")

    async def aboom(inputs):
        raise ValueError("bad")

    with pytest.raises(KeyError):
        asyncio.run(run_task(boom, {}))
    with pytest.raises(ValueError):
        asyncio.run(run_task(aboom, {}, timeout=5))


def test_a_timeout_raised_by_the_task_is_not_mistaken_for_our_timeout():
    async def flaky(inputs):
        raise TimeoutError("the API timed out")

    with pytest.raises(TimeoutError) as e:
        asyncio.run(run_task(flaky, {}, timeout=5))
    assert not isinstance(e.value, TaskTimeoutError)


def test_async_timeout_cancels_the_task():
    state = {"cancelled": False}

    async def slow(inputs):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def main():
        t0 = time.perf_counter()
        with pytest.raises(TaskTimeoutError, match="0.05"):
            await run_task(slow, {}, timeout=0.05)
        return time.perf_counter() - t0

    assert asyncio.run(main()) < 1 and state["cancelled"]


def test_sync_timeout_returns_control_quickly():
    def slow(inputs):
        time.sleep(0.4)

    async def main():
        t0 = time.perf_counter()
        with pytest.raises(TaskTimeoutError):
            await run_task(slow, {}, timeout=0.05)
        return time.perf_counter() - t0

    assert asyncio.run(main()) < 0.3   # we stopped waiting; the thread finishes on its own


def test_no_timeout_hit_returns_the_value():
    async def quick(inputs):
        return "ok"

    assert asyncio.run(run_task(quick, {}, timeout=5)) == "ok"


def test_bad_arguments_are_refused_early():
    with pytest.raises(TypeError):
        asyncio.run(run_task("not callable", {}))
    with pytest.raises(ValueError):
        asyncio.run(run_task(lambda i: 1, {}, timeout=0))


VAR = contextvars.ContextVar("v", default="none")


def test_task_sees_the_callers_context_but_cannot_leak_changes_back():
    async def a(inputs):
        seen = VAR.get()
        VAR.set("changed-by-task")
        return seen

    def s(inputs):
        seen = VAR.get()
        VAR.set("changed-by-thread")
        return seen

    async def main():
        VAR.set("caller")
        out = [await run_task(a, {}), await run_task(s, {}),
               await run_task(a, {}, timeout=1), await run_task(s, {}, timeout=1)]
        return out, VAR.get()

    out, after = asyncio.run(main())
    assert out == ["caller"] * 4      # this is what makes trace spans nest under the case span
    assert after == "caller"          # and one task can't disturb the next


# ====================================== all three pieces together (a preview of step 5)

def test_registry_task_and_evaluators_fit_together():
    
    @register("contains_expected")
    class ContainsExpected(Evaluator):
        async def score(self, case, output):
            expected = (case.expectations or {}).get("answer")
            if expected is None:
                return self.skipped("no expected answer")
            return self.result(1.0 if expected in output else 0.0)

    evaluators = build_evaluators(["contains_expected"])
    task = lambda inputs: f"{inputs['message']} -> hello there"

    async def main():
        output = await run_task(task, CASE.inputs, timeout=5)
        return [await ev.score(CASE, output) for ev in evaluators]

    (score,) = asyncio.run(main())
    assert score.name == "contains_expected" and score.value == 1.0 and score.passed is True
    no_expectation = Record("c2", {"message": "hi"})
    assert asyncio.run(evaluators[0].score(no_expectation, "x")).status == "skipped"