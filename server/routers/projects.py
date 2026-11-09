from fastapi import APIRouter, Depends , HTTPException, status
from typing import List, Optional
from app.db import get_db
from sqlalchemy.orm import Session
from app import models,schemas

router = APIRouter(prefix="/v1/projects", tags=["Projects"])

@router.get("", response_model=List[schemas.ProjectRead])
def get_projects(name: Optional[str] = None,skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(models.Project)
    if name:
        query = query.filter(models.Project.name.ilike(f"%{name}%"))
    projects = query.offset(skip).limit(limit).all()
    return projects

@router.get("/{project_id}/experiments", response_model=List[schemas.ExperimentRead])
def get_project_experiments(project_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    
    experiments = db.query(models.Experiment).filter(models.Experiment.project_id == project_id).offset(skip).limit(limit).all()
    return experiments

@router.post("", response_model=schemas.ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project( project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    existing_project = db.query(models.Project).filter(models.Project.name == project.name).first()
    if existing_project:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="Project with this name already exists")
    db_project = models.Project(name=project.name)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    
    return db_project

@router.post("/{project_id}/experiments", response_model=schemas.ExperimentRead, status_code=status.HTTP_201_CREATED)
def create_experiment(project_id: int, experiment: schemas.ExperimentCreate, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    experiment_name = db.query(models.Experiment).filter(models.Experiment.project_id == project_id,
        models.Experiment.name == experiment.name).first()
    if experiment_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An experiment with this name already exists in this project")

    db_experiment = models.Experiment(name=experiment.name, project_id=project_id)
    db.add(db_experiment)
    db.commit()
    db.refresh(db_experiment)
    
    return db_experiment

