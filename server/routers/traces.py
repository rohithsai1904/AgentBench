from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
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

@router.get("/{trace_id}", response_model=schemas.TraceRead)
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    trace = db.get(models.Trace, trace_id)
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return trace