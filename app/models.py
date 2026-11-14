from sqlalchemy import Column, Integer, String, UniqueConstraint, ForeignKey, DateTime, Text, func, Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
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
    name = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True),server_default=func.now())

    project = relationship("Project", back_populates="experiments")
    traces = relationship("Trace", back_populates="experiment")

class Trace(Base):
    __tablename__ = "traces"
    id = Column(String(32), primary_key=True)  # the SDK makes this, it's a hex string
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(300), nullable=False)
    status = Column(String(16), nullable=False, default="ok")
    input = Column(JSONB(none_as_null=True))
    output = Column(JSONB(none_as_null=True))
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)

    project = relationship("Project", back_populates="traces")
    experiment = relationship("Experiment", back_populates="traces")
    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan", foreign_keys="Span.trace_id")

class Span(Base):
    __tablename__ = "spans"
    # span ids are random 64-bit values, so scope them to their trace
    trace_id = Column(String(32), ForeignKey("traces.id", ondelete="CASCADE"), primary_key=True)
    id = Column(String(32), primary_key=True)
    # deliberately NOT a foreign key: a child can arrive before its parent
    parent_span_id = Column(String(32), nullable=True, index=True)
    name = Column(String(300), nullable=False)
    kind = Column(String(32), nullable=False, default="function")
    status = Column(String(16), nullable=False, default="ok")
    input = Column(JSONB(none_as_null=True))
    output = Column(JSONB(none_as_null=True))
    error_type = Column(String(200))
    error_message = Column(Text)
    error_stacktrace = Column(Text)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    attributes = Column(JSONB, default=dict)

    trace = relationship("Trace", back_populates="spans", foreign_keys=[trace_id])

class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_dataset_name_version"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    version = Column(String(16), nullable=False)     
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    records = relationship(
        "Record",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

class Record(Base):
    __tablename__ = "records"

    id = Column(String, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),primary_key=True)
    inputs = Column(JSONB(none_as_null=True), nullable=False)
    expectations = Column(JSONB(none_as_null=True), nullable=True)
    tags = Column(JSONB, nullable=False, default=list)
    meta = Column("metadata", JSONB, nullable=False, default=dict)

    dataset = relationship("Dataset", back_populates="records")