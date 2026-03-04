from __future__ import annotations

from typing import TypedDict

from jobfinder.models.domain import (
    LLMFit,
    NormalizedJobPosting,
    RankedJob,
    RawJobPosting,
    RunResult,
    SearchProfile,
    SourceRunStatus,
)


class JobFinderState(TypedDict, total=False):
    profile: SearchProfile
    run_result: RunResult
    crawl_only: bool

    query_terms: list[str]
    source_statuses: list[SourceRunStatus]

    raw_jobs_by_source: dict[str, list[RawJobPosting]]
    normalized_jobs: list[NormalizedJobPosting]

    job_map: dict[str, tuple[int, bool]]

    rule_scores: dict[str, float]
    rule_rationales: dict[str, str]
    candidate_jobs: list[NormalizedJobPosting]

    semantic_scores: dict[str, float]
    llm_fits: dict[str, LLMFit]

    ranked_jobs: list[RankedJob]
