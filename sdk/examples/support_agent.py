"""Customer-support agent: two tools + one LLM call (the Week 1 acceptance scenario).

    support_agent            [agent]
    |- lookup_order          [tool]
    |  `- db_query           [function]
    |- anthropic.messages.create [llm]
    `- issue_refund          [tool]       (only if the LLM decides to refund)

The "LLM" is a fake client with the same shape as Anthropic's, so the demo runs offline.
To use the real one, replace FakeAnthropic() with anthropic.Anthropic() (one line).

    python examples/support_agent.py                          # local: prints the trees
    python examples/support_agent.py http://localhost:8000    # sends traces to your server
"""
import re
import sys
import time
from dataclasses import dataclass

import agentbench
from agentbench import finished_spans, instrument_anthropic, observe, print_tree, tool, trace

ORDERS = {
    "A-1001": {"id": "A-1001", "item": "Headphones", "total": 129.0, "days_since_delivery": 3},
    "A-1002": {"id": "A-1002", "item": "USB-C cable", "total": 12.5, "days_since_delivery": 90},
}


# ---------------------------------------------------------------- fake LLM client
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
        time.sleep(0.06)  # pretend network time
        user = messages[-1]["content"]
        days = re.search(r"days_since_delivery': (\d+)", user)
        if "ORDER_NOT_FOUND" in user:
            text = "I couldn't find that order, could you double-check the number? ACTION: none"
        elif days and int(days.group(1)) > 30:
            text = "Sorry, that order is outside our 30-day refund window. ACTION: none"
        else:
            text = "I'm sorry about that! I've started a refund for you. ACTION: refund"
        tokens_in = len((system + user).split())
        return Response(model=model, content=[TextBlock(text)], usage=Usage(tokens_in, len(text.split())))


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


client = instrument_anthropic(FakeAnthropic())   # every client.messages.create(...) is now traced


# -------------------------------------------------------------------------- tools
@observe(name="db_query")
def db_query(table, key):
    time.sleep(0.02)  # pretend I/O
    if table == "orders" and key in ORDERS:
        return ORDERS[key]
    raise KeyError(f"No order {key!r}")


@tool
def lookup_order(order_id):
    return db_query("orders", order_id)


@tool
def issue_refund(order_id, amount):
    time.sleep(0.03)
    return {"refund_id": f"R-{order_id}", "amount": amount, "status": "issued"}


# -------------------------------------------------------------------------- agent
@trace(name="support_agent")
def run_support_agent(customer_message, order_id):
    try:
        order = lookup_order(order_id)
        context = f"ORDER: {order}"
    except KeyError:  # the tool span stays marked as an error; the agent carries on
        order, context = None, "ORDER_NOT_FOUND"

    response = client.messages.create(
        model="fake-claude-1",
        max_tokens=200,
        system="You are a helpful customer-support agent. Refund within 30 days.",
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


SCENARIOS = [
    ("My headphones arrived broken, I want my money back.", "A-1001"),  # refund
    ("Please refund order A-9999.", "A-9999"),                          # tool error, recovers
    ("This cable stopped working.", "A-1002"),                          # too old, no refund
]


def main():
    server = sys.argv[1] if len(sys.argv) > 1 else None
    if server:
        agentbench.init(server, project="customer-support")
    for message, order_id in SCENARIOS:
        result = run_support_agent(message, order_id)
        print(f"{order_id}: {result['reply']}   (trace {result['trace_id']})")
    if not server:
        print()
        print_tree(finished_spans)


if __name__ == "__main__":
    main()