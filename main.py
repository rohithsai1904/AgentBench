from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine, Base, get_db
from contextlib import asynccontextmanager
from server.routers import ingest,traces,projects,dataset

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(traces.router)
app.include_router(dataset.router)

@app.get("/healthz")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}