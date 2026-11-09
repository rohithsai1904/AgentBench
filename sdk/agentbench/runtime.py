from __future__ import annotations

from typing import Optional

from .client import AgentBench
from .tracing import set_exporter, trace_payload


def init(
    base_url: str = "http://localhost:8000",
    project: str = "default",
    api_key: Optional[str] = None,
    client: Optional[AgentBench] = None,
) -> AgentBench:
    """Connect to the server, find-or-create the project, and start sending traces.

    Raises if the server can't be reached right now (a wrong URL should fail loudly).
    After that, export failures are logged and never raised into your code.
    """
    client = client or AgentBench(base_url, api_key)
    project_id = client.get_or_create_project(project)["id"]

    def export(root, spans):
        client.ingest([trace_payload(project_id, root, spans)])

    set_exporter(export)
    return client