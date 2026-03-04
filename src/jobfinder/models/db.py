from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(primary_key=True)
    profile_id: str = Field(index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    completed_at: datetime | None = None
    status: str = Field(default="running", index=True)
    warning_count: int = 0
    error_count: int = 0


class RunSourceStatusRecord(SQLModel, table=True):
    __tablename__ = "run_source_status"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    source: str = Field(index=True)
    status: str
    fetched_count: int = 0
    normalized_count: int = 0
    error: str | None = None


class JobRecord(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    company: str = Field(index=True)
    source_job_id: str = Field(index=True)
    url: str
    title: str = Field(index=True)
    location_text: str = Field(index=True)
    is_remote: bool = Field(default=False)
    latest_content_hash: str = Field(index=True)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class JobVersionRecord(SQLModel, table=True):
    __tablename__ = "job_versions"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    run_id: str = Field(index=True)
    content_hash: str = Field(index=True)
    raw_snapshot_id: str = Field(index=True)
    description_text: str
    employment_type: str | None = None
    seniority: str | None = None
    posted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class AlertRecord(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    job_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class JobScoreRecord(SQLModel, table=True):
    __tablename__ = "job_scores"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    job_id: int = Field(index=True)
    rule_score: float = 0.0
    semantic_score: float = 0.0
    llm_score: float = 0.0
    total_score: float = Field(index=True)
    rationale: str = ""
    llm_reasoning: str = ""
    is_new_alert: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class ProfileSnapshotRecord(SQLModel, table=True):
    __tablename__ = "profile_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    profile_id: str = Field(index=True)
    payload_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
