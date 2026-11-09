from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/v1", tags=["Ingest"])

TRACE_FIELDS = ("experiment_id", "name", "status", "input", "output", "start_time", "end_time", "duration_ms")
SPAN_FIELDS = (
    "parent_span_id", "name", "kind", "status", "input", "output",
    "error_type", "error_message", "error_stacktrace",
    "start_time", "end_time", "duration_ms", "attributes",
)


@router.post("/ingest", response_model=schemas.IngestResponse)
def ingest(payload: schemas.IngestRequest, db: Session = Depends(get_db)):
    # 1. every referenced project / experiment must exist
    project_ids = {t.project_id for t in payload.traces}
    found = {pid for (pid,) in db.query(models.Project.id).filter(models.Project.id.in_(project_ids))}
    if missing := project_ids - found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown project id(s): {sorted(missing)}")
    
    for t in payload.traces:
        if t.experiment_id is not None and db.get(models.Experiment, t.experiment_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown experiment id: {t.experiment_id}")

    # 2. upsert: create what's new, update what already exists (so retries are safe)
    span_count = 0
    for t in payload.traces:
        trace = db.get(models.Trace, t.id)
        if trace is None:
            trace = models.Trace(id=t.id, project_id=t.project_id)
            db.add(trace)
        elif trace.project_id != t.project_id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Trace {t.id} belongs to another project")
        for f in TRACE_FIELDS:
            setattr(trace, f, getattr(t, f))

        existing = {s.id: s for s in db.query(models.Span).filter(models.Span.trace_id == t.id)}
        for s in t.spans:
            row = existing.get(s.id)
            if row is None:
                row = models.Span(trace_id=t.id, id=s.id)
                db.add(row)
            for f in SPAN_FIELDS:
                setattr(row, f, getattr(s, f))
        span_count += len(t.spans)

    # 3. one commit: all or nothing
    try:
        db.commit()
    except IntegrityError:  # two requests inserted the same new trace at the same moment
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Concurrent write to the same trace, retry")
    return schemas.IngestResponse(traces=len(payload.traces), spans=span_count)