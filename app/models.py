from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import relationship
from app.db import Base


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True),server_default=func.now())
    
    experiments = relationship("Experiment", back_populates="project", cascade="all, delete-orphan")
    traces = relationship("Trace", back_populates="project", cascade="all, delete-orphan")


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String,unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True),server_default=func.now())

    project = relationship("Project", back_populates="experiments")
    traces = relationship("Trace", back_populates="experiment")

class Trace(Base):
    __tablename__ = "traces"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    experiment_id = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="traces")
    experiment = relationship("Experiment", back_populates="traces")
    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan", foreign_keys="Span.trace_id")

class Span(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(Integer, ForeignKey("traces.id",ondelete="CASCADE"),nullable=False)
    parent_span_id = Column(Integer,ForeignKey("spans.id",ondelete="CASCADE"),nullable=False)
    name = Column(String(255), nullable=False)
    kind = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    input = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)

    trace = relationship("Trace",back_populates="spans", foreign_keys=[trace_id])
    parent = relationship("Span", remote_side=[id], back_populates="children", foreign_keys=[parent_span_id])
    children = relationship("Span", back_populates="parent", cascade="all, delete-orphan")