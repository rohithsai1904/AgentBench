from pydantic import BaseModel, ConfigDict

from datetime import datetime

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