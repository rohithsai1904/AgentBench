import agentbench
from agentbench import trace, tool

agentbench.init("http://localhost:8000", project="support")

@tool
def lookup_order(order_id):
    return {"id": order_id}

@trace(name="support_agent")
def agent(order_id):
    return lookup_order(order_id)

agent("A-1")