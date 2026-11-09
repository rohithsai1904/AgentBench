"""A research agent whose trace has: 5 levels of nesting, parallel async tools,
a retry (one failed span + one good span), a thread, LLM spans, and a manual span.

    python complex_trace.py                         # local mode: prints the tree
    python complex_trace.py http://localhost:8000   # sends traces to your server
"""
import asyncio
import sys
import time

import agentbench
from agentbench import finished_spans, llm, observe, print_tree, span, tool, trace


@observe
def parse_results(raw):                      # level 5: plain helper
    time.sleep(0.005)
    return [r.strip() for r in raw.split(";")]


@tool
async def search_web(query, flaky=False):    # level 4: a tool that can fail
    await asyncio.sleep(0.03)
    if flaky:
        raise TimeoutError(f"search timed out for {query!r}")
    return parse_results("source A; source B; source C")


@observe(name="search_with_retry")           # level 3: retries -> 2 child spans, 1st one errors
async def search_with_retry(query, first_attempt_fails=False):
    try:
        return await search_web(query, flaky=first_attempt_fails)
    except TimeoutError:
        return await search_web(query)


@llm(name="plan")
async def make_plan(question):
    await asyncio.sleep(0.05)
    agentbench.current_span().attributes.update({"llm.model": "stub-1", "llm.input_tokens": 42, "llm.output_tokens": 18})
    return {"queries": ["background", "recent news", "expert views"]}


@observe
async def gather_sources(queries):           # level 2: fan-out, 3 searches in parallel
    return await asyncio.gather(
        *[search_with_retry(q, first_attempt_fails=(i == 1)) for i, q in enumerate(queries)]
    )


@tool
def check_facts(sources):                    # blocking tool, will run in a thread
    time.sleep(0.04)
    return {"verified": len(sources), "disputed": 0}


@llm(name="write_answer")
async def write_answer(question, verdict, fail=False):
    await asyncio.sleep(0.06)
    agentbench.current_span().attributes.update({"llm.model": "stub-1", "llm.input_tokens": 310, "llm.output_tokens": 95})
    if fail:
        raise RuntimeError("model overloaded")
    return f"Answer to {question!r} based on {verdict['verified']} verified sources."


@trace(name="research_assistant")
async def research_assistant(question, fail=False):
    plan = await make_plan(question)
    sources = await gather_sources(plan["queries"])
    with span("rank_sources") as s:          # a manual span, no decorator
        ranked = sorted({x for group in sources for x in group})
        s.output = ranked
    verdict = await asyncio.to_thread(check_facts, ranked)   # to_thread copies the context
    return await write_answer(question, verdict, fail=fail)


def main():
    server = sys.argv[1] if len(sys.argv) > 1 else None
    if server:
        agentbench.init(server, project="research")
    print(asyncio.run(research_assistant("Why is the sky blue?")))
    try:                                      # a second trace whose ROOT ends in an error
        asyncio.run(research_assistant("What is dark matter?", fail=True))
    except RuntimeError as e:
        print("agent failed:", e)
    if not server:
        print()
        print_tree(finished_spans)


if __name__ == "__main__":
    main()