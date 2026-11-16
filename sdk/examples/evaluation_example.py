"""Customer-support agent + its evaluation"""
import asyncio
import re
import time,pytest,json
from dataclasses import dataclass

import agentbench
from agentbench import finished_spans, instrument_anthropic, observe, print_tree, tool, trace
from agentbench.datasets import Record, Dataset, _generate_version
from agentbench.evaluation import Evaluator,build_evaluators, get_evaluator,list_evaluators, register, run_dataset,UnknownEvaluatorError

ORDERS = {
    "A-1001": {"id": "A-1001", "item": "Headphones", "total": 129.0, "days_since_delivery": 3},
    "A-1002": {"id": "A-1002", "item": "USB-C cable", "total": 12.5, "days_since_delivery": 90},
    "A-1003": {"id": "A-1003", "item": "Keyboard", "total": 59.0, "days_since_delivery": 45},   # NEW
}


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class TextBlock:
    text: str


@dataclass
class Response:
    model: str
    content: list
    usage: Usage


class FakeMessages:
    def create(self, *, model, max_tokens, system, messages):
        time.sleep(0.01)
        user = messages[-1]["content"]
        days = re.search(r"days_since_delivery': (\d+)", user)
        window = int(re.search(r"within (\d+) days", system).group(1))          # EDIT 1: read policy from the prompt

        if "ORDER_NOT_FOUND" in user:
            text = "I couldn't find that order, could you double-check the number? ACTION: none"
        elif days and int(days.group(1)) > window:
            text = f"Sorry, that order is outside our {window}-day refund window. ACTION: none"
        else:
            text = "I'm sorry about that! I've started a refund for you. ACTION: refund"

        tokens_in = len((system + user).split())
        return Response(model=model, content=[TextBlock(text)], usage=Usage(tokens_in, len(text.split())))


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


client = instrument_anthropic(FakeAnthropic())


@observe(name="db_query")
def db_query(table, key):
    time.sleep(0.002)
    if table == "orders" and key in ORDERS:
        return ORDERS[key]
    raise KeyError(f"No order {key!r}")


@tool
def lookup_order(order_id):
    return db_query("orders", order_id)


@tool
def issue_refund(order_id, amount):
    return {"refund_id": f"R-{order_id}", "amount": amount, "status": "issued"}


@trace(name="support_agent")
def run_support_agent(customer_message, order_id, policy_days=30):           # EDIT 2: policy_days parameter
    try:
        order = lookup_order(order_id)
        context = f"ORDER: {order}"
    except KeyError:
        order, context = None, "ORDER_NOT_FOUND"

    response = client.messages.create(
        model="fake-claude-1",
        max_tokens=200,
        system=f"You are a helpful customer-support agent. Refund within {policy_days} days.",   # EDIT 3
        messages=[{"role": "user", "content": f"{customer_message}\n{context}"}],
    )
    text = response.content[0].text

    refund = None
    if "ACTION: refund" in text and order:
        refund = issue_refund(order["id"], order["total"])
    return {
        "reply": text.split(" ACTION")[0],
        "refund": refund,
        "trace_id": agentbench.current_span().trace_id,
    }


# ============================================================== DATASETS
def case(id, message, order_id, *, refund, contains):
    return Record(
        id,
        {"customer_message": message, "order_id": order_id},      # the agent's arguments, by name
        {"refund": refund, "reply_contains": contains},          # what a correct answer looks like
    )


r1 = case("r1", "My headphones arrived broken, I want my money back.", "A-1001", refund=True,  contains="refund for you")
r2 = case("r2", "Please refund order A-9999.",                        "A-9999", refund=False, contains="couldn't find")
r3 = case("r3", "This cable stopped working.",                        "A-1002", refund=False, contains="outside")
r4 = case("r4", "My keyboard has a dead key, refund please.",         "A-1003", refund=True,  contains="refund for you")  # 45 days: v1 gets it wrong
r5 = case("r5", "Headphones mic is faulty, I want a refund.",         "A-1001", refund=True,  contains="refund for you")
r6 = case("r6", "Refund my missing order A-8888.",                    "A-8888", refund=False, contains="couldn't find")

dataset_d1 = Dataset("support", (r1, r2, r3), _generate_version((r1, r2, r3)))
dataset_d2 = dataset_d1.add_records((r4, r5, r6))                # new version, d1 is untouched


# ============================================================== EVALUATORS
@register("refund_decision")
class RefundDecision(Evaluator):
    async def score(self, case, output):
        if "refund" not in case.expectations:
            return self.skipped("case has no expected refund decision")
        expected = case.expectations["refund"]
        got = output["refund"] is not None
        return self.result(1.0 if got == expected else 0.0, f"expected refund={expected}, got refund={got}")


@register("reply_contains")
class ReplyContains(Evaluator):
    def __init__(self, case_sensitive=False, **kw):
        super().__init__(**kw)                                   # always call this
        self.case_sensitive = case_sensitive

    async def score(self, case, output):
        needle = case.expectations.get("reply_contains")
        if needle is None:
            return self.skipped("case has no expected phrase")
        reply = output["reply"]
        if not self.case_sensitive:
            reply, needle = reply.lower(), needle.lower()
        return self.result(1.0 if needle in reply else 0.0, f"looking for {needle!r}")


@register("always")
class Always(Evaluator):
    def __init__(self, value=1.0, **kw):
        super().__init__(**kw)
        self.value = value

    async def score(self, case, output):
        return self.result(self.value)


# ============================================================== CONFIG -> RUN
EVAL_CONFIG = [
    "refund_decision",                                           # by name
    {"type": "reply_contains", "case_sensitive": False},         # with options
    {"type": "always", "name": "smoke", "threshold": 0.5},       # renamed score
]


def make_task(policy_days):
    """The runner passes ONE dict (the inputs); the agent wants two arguments. This is the adapter."""
    def task(inputs):
        return run_support_agent(inputs["customer_message"], inputs["order_id"], policy_days=policy_days)
    return task


async def evaluate(dataset, policy_days):
    return await run_dataset(
        dataset,
        make_task(policy_days),
        build_evaluators(EVAL_CONFIG),
        config={"policy_days": policy_days},                     # stored on the run so you can find it later
    )


def summarize(run):
    """{evaluator: {"mean", "pass_rate", "scored", "skipped", "errored"}}"""
    out = {}
    for name in run.config["evaluators"]:
        scores = [s for c in run.cases if (s := c.score_for(name)) is not None]
        scored = [s for s in scores if s.value is not None]
        out[name] = {
            "mean": sum(s.value for s in scored) / len(scored) if scored else None,
            "pass_rate": sum(1 for s in scored if s.passed) / len(scored) if scored else None,
            "scored": len(scored),
            "skipped": sum(1 for s in scores if s.status == "skipped"),
            "errored": sum(1 for s in scores if s.status == "error"),
        }
    return out


def changed_cases(run_a, run_b, evaluator):
    """Case ids whose `passed` differs between two runs: (id, a_passed, b_passed)."""
    a = {c.case_id: c.score_for(evaluator) for c in run_a.cases}
    b = {c.case_id: c.score_for(evaluator) for c in run_b.cases}
    return [(i, a[i].passed, b[i].passed) for i in a if i in b and a[i] and b[i] and a[i].passed != b[i].passed]


if __name__ == "__main__":                                       # never run work at import time
    v1 = asyncio.run(evaluate(dataset_d2, policy_days=30))
    v2 = asyncio.run(evaluate(dataset_d2, policy_days=60))
    for label, run in (("v1 (30 days)", v1), ("v2 (60 days)", v2)):
        print(label, run.run_id[:8])
        for name, row in summarize(run).items():
            print(f"   {name:16} pass_rate={row['pass_rate']}")
    print("changed on refund_decision:", changed_cases(v1, v2, "refund_decision"))



# ==========================================================================
@pytest.fixture(autouse=True)
def clean_spans():
    agentbench.clear()
    yield
    agentbench.clear()


# ---------------------------------------------------------------- 1. registering
def test_decorator_registers_and_sets_name():
    assert {"refund_decision", "reply_contains", "always"} <= set(list_evaluators())
    assert RefundDecision.name == "refund_decision"

def test_registering_a_new_evaluator():
    @register("test_word_count")
    class WordCount(Evaluator):
        async def score(self, case, output):
            return self.result(1.0 if len(output["reply"].split()) < 30 else 0.0)

    assert "test_word_count" in list_evaluators()
    assert isinstance(get_evaluator("test_word_count"), WordCount)

def test_duplicate_name_for_a_different_class_is_refused():
    with pytest.raises(ValueError, match="already taken"):
        @register("refund_decision")
        class Impostor(Evaluator):
            async def score(self, case, output): ...

def test_register_rejects_non_evaluators():
    with pytest.raises(TypeError):
        @register("not_an_evaluator")
        class Nope: ...


# ---------------------------------------------------------------- 2. getting / building
def test_get_evaluator_passes_options():
    ev = get_evaluator("reply_contains", case_sensitive=True, threshold=0.9)
    assert ev.case_sensitive is True and ev.threshold == 0.9


def test_unknown_name_suggests_the_closest_one():
    with pytest.raises(UnknownEvaluatorError, match="refund_decision"):
        get_evaluator("refund_decison")


def test_bad_option_names_the_evaluator():
    with pytest.raises(TypeError, match="refund_decision"):
        get_evaluator("refund_decision", colour="red")


def test_bad_threshold_is_rejected():
    with pytest.raises(ValueError):
        get_evaluator("always", threshold=1.5)


def test_build_accepts_names_dicts_and_instances():
    mine = ReplyContains(name="polite", case_sensitive=True)
    built = build_evaluators(["refund_decision", {"type": "always", "name": "smoke"}, mine])
    assert [e.name for e in built] == ["refund_decision", "smoke", "polite"]
    assert built[2] is mine


def test_build_from_config_gives_the_expected_names():
    assert [e.name for e in build_evaluators(EVAL_CONFIG)] == ["refund_decision", "reply_contains", "smoke"]


def test_build_does_not_modify_the_config():
    before = json.dumps(EVAL_CONFIG, sort_keys=True)
    build_evaluators(EVAL_CONFIG)
    build_evaluators(EVAL_CONFIG)
    assert json.dumps(EVAL_CONFIG, sort_keys=True) == before


def test_build_gives_a_fresh_instance_each_time():
    a, b = build_evaluators(["always"]), build_evaluators(["always"])
    assert a[0] is not b[0]


def test_build_refuses_duplicate_names_and_asks_for_a_rename():
    with pytest.raises(ValueError, match="duplicate"):
        build_evaluators(["always", "always"])
    ok = build_evaluators(["always", {"type": "always", "name": "always_2"}])
    assert len(ok) == 2


def test_dict_spec_needs_a_type():
    with pytest.raises(ValueError, match="type"):
        build_evaluators([{"name": "x"}])


def test_passing_a_class_instead_of_an_instance_is_a_clear_error():
    with pytest.raises(TypeError):
        build_evaluators([RefundDecision])          # forgot the () / the name string


# ---------------------------------------------------------------- 3. the evaluators themselves
async def test_refund_decision_scores_each_way():
    ev = RefundDecision()
    right = await ev.score(r1, {"refund": {"amount": 1}})
    wrong = await ev.score(r1, {"refund": None})
    assert (right.value, right.passed) == (1.0, True)
    assert (wrong.value, wrong.passed) == (0.0, False)


async def test_missing_expectation_is_skipped_not_zero():
    bare = Record("x", {"customer_message": "hi", "order_id": "A-1001"})
    s = await RefundDecision().score(bare, {"refund": None})
    assert s.status == "skipped" and s.value is None


async def test_reply_contains_case_sensitivity():
    out = {"reply": "I've started a REFUND for you"}
    assert (await ReplyContains().score(r1, out)).value == 1.0
    assert (await ReplyContains(case_sensitive=True).score(r1, out)).value == 0.0


async def test_threshold_changes_passed_but_not_value():
    class Half(Evaluator):
        name = "half"
        async def score(self, case, output):
            return self.result(0.5)
    assert (await Half().score(r1, None)).passed is True                  # 0.5 >= 0.5
    assert (await Half(threshold=0.8).score(r1, None)).passed is False


# ---------------------------------------------------------------- 4. running
async def test_run_one_dataset_end_to_end():
    run = await evaluate(dataset_d1, policy_days=30)
    assert run.n_cases == 3 and run.n_errors == 0
    assert [c.case_id for c in run.cases] == ["r1", "r2", "r3"]           # order preserved
    assert run.dataset_version == dataset_d1.version
    assert run.config["evaluators"] == ["refund_decision", "reply_contains", "smoke"]
    assert run.config["policy_days"] == 30
    assert all(len(c.scores) == 3 for c in run.cases)


async def test_run_ids_are_unique_per_run():
    a = await evaluate(dataset_d1, 30)
    b = await evaluate(dataset_d1, 30)
    assert a.run_id != b.run_id


async def test_v1_vs_v2_prompt_comparison():
    v1 = await evaluate(dataset_d2, 30)
    v2 = await evaluate(dataset_d2, 60)
    assert summarize(v1)["refund_decision"]["pass_rate"] == pytest.approx(5 / 6)
    assert summarize(v2)["refund_decision"]["pass_rate"] == 1.0
    assert changed_cases(v1, v2, "refund_decision") == [("r4", False, True)]
    assert v1.config["policy_days"] != v2.config["policy_days"]


async def test_summarize_counts_skipped():
    bare = Record("bare", {"customer_message": "hi", "order_id": "A-1001"})   # no expectations
    run = await run_dataset(Dataset("tmp", (r1, bare), "v"), make_task(30), build_evaluators(EVAL_CONFIG))
    row = summarize(run)["refund_decision"]
    assert (row["scored"], row["skipped"]) == (1, 1)


# ---------------------------------------------------------------- 5. datasets & versions
def test_add_records_makes_a_new_version_and_leaves_the_old_one_alone():
    assert len(dataset_d1) == 3 and len(dataset_d2) == 6
    assert dataset_d1.version != dataset_d2.version
    assert dataset_d1.version == _generate_version(dataset_d1.records)


# ---------------------------------------------------------------- 6. failures stay contained
async def test_a_crashing_case_does_not_stop_the_run():
    def flaky(inputs):
        if inputs["order_id"] == "A-1002":
            raise RuntimeError("model exploded")
        return run_support_agent(inputs["customer_message"], inputs["order_id"])

    run = await run_dataset(dataset_d1, flaky, build_evaluators(EVAL_CONFIG))
    bad = next(c for c in run.cases if c.case_id == "r3")
    assert "model exploded" in bad.error
    assert [s.status for s in bad.scores] == ["skipped"] * 3              # skipped, not a fake 0
    assert run.n_errors == 1
    assert all(c.ok for c in run.cases if c.case_id != "r3")


async def test_a_crashing_evaluator_only_affects_its_own_score():
    @register("test_boom")
    class Boom(Evaluator):
        async def score(self, case, output):
            raise ValueError("bad evaluator")

    run = await run_dataset(dataset_d1, make_task(30), build_evaluators(["test_boom", "refund_decision"]))
    for c in run.cases:
        assert c.score_for("test_boom").status == "error"
        assert c.score_for("refund_decision").status == "scored"


async def test_slow_task_times_out_but_others_finish():
    import time
    def slow(inputs):
        if inputs["order_id"] == "A-1002":
            time.sleep(0.5)
        return run_support_agent(inputs["customer_message"], inputs["order_id"])

    run = await run_dataset(dataset_d1, slow, build_evaluators(["refund_decision"]), timeout=0.1)
    assert "timed out" in next(c for c in run.cases if c.case_id == "r3").error.lower() or "Timeout" in next(c for c in run.cases if c.case_id == "r3").error
    assert sum(c.ok for c in run.cases) == 2


async def test_wrong_task_signature_is_reported_per_case_not_raised():
    run = await run_dataset(dataset_d1, run_support_agent, build_evaluators(["always"]))   # forgot the adapter
    assert run.n_errors == 3 and "TypeError" in run.cases[0].error


# ---------------------------------------------------------------- 7. tracing + serialisation
def _spans():
    fs = agentbench.finished_spans          # a list in some versions, a function in others
    return list(fs() if callable(fs) else fs)


async def test_every_case_has_a_trace_and_the_run_id_is_on_the_root_span():
    run = await evaluate(dataset_d1, 30)
    spans = _spans()
    roots = [s for s in spans if s.name == "eval_case"]
    assert len(roots) == 3
    assert {s.attributes["run_id"] for s in roots} == {run.run_id}
    assert {c.trace_id for c in run.cases} == {s.trace_id for s in roots}
    # the agent's own spans hang under the case span, in the same trace
    for c in run.cases:
        names = {s.name for s in spans if s.trace_id == c.trace_id}
        assert {"eval_case", "support_agent", "lookup_order"} <= names


async def test_run_result_is_json_serialisable():
    run = await evaluate(dataset_d2, 60)
    data = json.loads(json.dumps(run.to_dict()))
    assert data["run_id"] == run.run_id and len(data["cases"]) == 6
    assert data["cases"][0]["scores"][0]["name"] == "refund_decision"