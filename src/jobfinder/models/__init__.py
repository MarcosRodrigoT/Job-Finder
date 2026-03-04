"""Data models for JobFinder."""

from .db import (
    AlertRecord,
    JobRecord,
    JobScoreRecord,
    JobVersionRecord,
    ProfileSnapshotRecord,
    RunRecord,
    RunSourceStatusRecord,
)
from .domain import (
    NormalizedJobPosting,
    RankedJob,
    RawJobPosting,
    RunResult,
    ScoreBreakdown,
    ScoringWeights,
    SearchProfile,
    SourceRunStatus,
)

__all__ = [
    "AlertRecord",
    "JobRecord",
    "JobScoreRecord",
    "JobVersionRecord",
    "NormalizedJobPosting",
    "ProfileSnapshotRecord",
    "RankedJob",
    "RawJobPosting",
    "RunRecord",
    "RunResult",
    "RunSourceStatusRecord",
    "ScoreBreakdown",
    "ScoringWeights",
    "SearchProfile",
    "SourceRunStatus",
]
