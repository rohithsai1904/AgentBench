from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

class ProjectCreate(BaseModel):
    name : str

class ProjectRead(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ExperimentCreate(BaseModel):
    name: str

class ExperimentRead(BaseModel):
    id: int
    project_id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SpanIn(BaseModel):
    id: str
    parent_span_id: Optional[str] = None
    name: str
    kind: str = "function"
    status: str = "ok"
    input: Any = None
    output: Any = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_stacktrace: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceIn(BaseModel):
    id: str
    project_id: int
    experiment_id: Optional[int] = None
    name: str
    status: str = "ok"
    input: Any = None
    output: Any = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    spans: list[SpanIn] = Field(min_length=1)


class IngestRequest(BaseModel):
    traces: list[TraceIn] = Field(min_length=1)


class IngestResponse(BaseModel):
    traces: int
    spans: int