from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.build_tree import build_tree
from app.db import get_db

router = APIRouter(prefix="/v1/traces", tags=["Traces"])


@router.get("", response_model=List[schemas.TraceRead])
def list_traces(
    project_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Trace)
    if project_id is not None:
        query = query.filter(models.Trace.project_id == project_id)
    if status_filter:
        query = query.filter(models.Trace.status == status_filter)
    return query.order_by(models.Trace.start_time.desc()).limit(limit).offset(offset).all()

@router.get("/{trace_id}", response_model=schemas.TraceDetail)
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    trace = db.get(models.Trace, trace_id)
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    spans = [schemas.SpanRead.model_validate(s).model_dump() for s in trace.spans]
    return schemas.TraceDetail(
        id=trace.id,
        project_id=trace.project_id,
        experiment_id=trace.experiment_id,
        name=trace.name,
        status=trace.status,
        start_time=trace.start_time,
        end_time=trace.end_time,
        duration_ms=trace.duration_ms,
        input=trace.input,
        output=trace.output,
        tree=build_tree(spans),
    )