from sqlite3 import IntegrityError
from fastapi import APIRouter, Depends , HTTPException, status
from typing import Optional,List
from app import models,schemas
from sqlalchemy.orm import Session
from app.db import get_db

router = APIRouter(prefix="/v1/dataset", tags=["DataSet"])


@router.post("", response_model=schemas.DataSetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(dataset: schemas.DataSetCreate, db: Session = Depends(get_db)):

    exists = db.query(models.Dataset).filter(models.Dataset.name==dataset.name,models.Dataset.version==dataset.version).first()
    if exists:
        raise HTTPException(status_code=409, detail="Dataset with this name and version already exists")

    db_dataset = models.Dataset(name=dataset.name, version=dataset.version,
    records=[models.Record(id=r.id,inputs=r.inputs,expectation=r.expectations,tags=r.tags,meta=r.metadata) for r in dataset.records])

    db.add(db_dataset)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,"Dataset with this name and version already exists")
    db.refresh(db_dataset)
    return db_dataset

@router.get("", response_model=List[schemas.DatasetRead])
def list_dataset(name: Optional[str] = None,skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(models.Dataset)
    if name:
        query = query.filter(models.Dataset.name.ilike(f"%{name}%"))
    datasets = query.offset(skip).limit(limit).all()
    return datasets

@router.get("/{dataset_id}", response_model=schemas.DatasetRead)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    db_dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return db_dataset

@router.get("/name/{name}/", response_model=schemas.DatasetRead)
def get_dataset_by_name(name: str, version: str = "latest", db: Session = Depends(get_db)):
    if version=="latest":
        db_dataset = db.query(models.Dataset).filter(models.Dataset.name == name).order_by(models.Dataset.created_at.desc()).first()
        if not db_dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        db_dataset
    else:
        db_dataset = db.query(models.Dataset).filter(
            models.Dataset.name == name,
            models.Dataset.version == version
        ).first()

        if not db_dataset:
            raise HTTPException(status_code=404,detail="Dataset with this name and version not found")

    return db_dataset
