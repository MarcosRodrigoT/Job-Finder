from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ScoringWeights(BaseModel):
    rule: float = Field(default=0.35, ge=0.0, le=1.0)
    semantic: float = Field(default=0.30, ge=0.0, le=1.0)
    llm: float = Field(default=0.35, ge=0.0, le=1.0)


class SearchProfile(BaseModel):
    profile_id: str
    display_name: str = "Default Profile"
    target_roles: list[str]
    role_synonyms: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=lambda: ["Madrid", "Spain"])
    location_policy: str = "madrid_or_spain_remote"
    source_enabled: dict[str, bool] = Field(default_factory=dict)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    digest_size: int = Field(default=15, ge=1, le=100)
    dedup_days: int = Field(default=90, ge=1, le=365)

    def role_terms(self) -> list[str]:
        return list(dict.fromkeys([*self.target_roles, *self.role_synonyms]))


class RawJobPosting(BaseModel):
    source: str
    company: str
    payload: dict[str, Any]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None


class NormalizedJobPosting(BaseModel):
    source: str
    company: str
    source_job_id: str
    url: HttpUrl | str
    title: str
    location_text: str
    is_remote: bool = False
    posted_at: datetime | None = None
    description_text: str = ""
    employment_type: str | None = None
    seniority: str | None = None
    raw_snapshot_id: str
    content_hash: str

    def fingerprint(self) -> str:
        return f"{self.source}:{self.source_job_id}"


class SourceStatus(str, Enum):
    success = "success"
    error = "error"
    blocked = "blocked"
    skipped = "skipped"


class SourceRunStatus(BaseModel):
    source: str
    status: SourceStatus
    fetched_count: int = 0
    normalized_count: int = 0
    error: str | None = None


class LLMFit(BaseModel):
    role_fit: float = Field(default=0.0, ge=0.0, le=10.0)
    research_fit: float = Field(default=0.0, ge=0.0, le=10.0)
    location_fit: float = Field(default=0.0, ge=0.0, le=10.0)
    seniority_fit: float = Field(default=0.0, ge=0.0, le=10.0)
    reasoning: str = ""


class ScoreBreakdown(BaseModel):
    rule: float = Field(default=0.0, ge=0.0, le=100.0)
    semantic: float = Field(default=0.0, ge=0.0, le=100.0)
    llm: float = Field(default=0.0, ge=0.0, le=100.0)
    total: float = Field(default=0.0, ge=0.0, le=100.0)
    rationale: str = ""


class RankedJob(BaseModel):
    job: NormalizedJobPosting
    score: ScoreBreakdown
    llm_fit: LLMFit = Field(default_factory=LLMFit)
    is_new_alert: bool = False


class RunResult(BaseModel):
    run_id: str
    profile_id: str
    started_at: datetime
    completed_at: datetime | None = None
    source_statuses: list[SourceRunStatus] = Field(default_factory=list)
    total_raw_jobs: int = 0
    total_normalized_jobs: int = 0
    total_ranked_jobs: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    top_jobs: list[RankedJob] = Field(default_factory=list)
    report_markdown_path: str | None = None
    report_json_path: str | None = None
