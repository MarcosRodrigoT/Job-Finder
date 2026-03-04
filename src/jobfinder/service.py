from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jobfinder.adapters.registry import build_adapters
from jobfinder.config import DEFAULT_USER_AGENT, AppSettings, ensure_directories, load_profiles
from jobfinder.graph import JobFinderWorkflow, WorkflowDependencies
from jobfinder.models.domain import LLMFit, NormalizedJobPosting, RankedJob, RunResult, ScoreBreakdown, SourceRunStatus, SourceStatus
from jobfinder.reporting import write_run_reports
from jobfinder.scoring import OllamaFitScorer
from jobfinder.storage import JobRepository, RawSnapshotStore, SemanticVectorIndex

logger = logging.getLogger(__name__)


@dataclass
class RuntimeContext:
    settings: AppSettings
    profiles: dict
    repository: JobRepository
    snapshots: RawSnapshotStore


def build_runtime(config_path: Path = Path("config/search_profiles.yaml")) -> RuntimeContext:
    settings = AppSettings()
    if "jobfinder-bot" in settings.user_agent.lower():
        logger.warning(
            "Detected deprecated bot-style user-agent from environment; overriding to browser-like user-agent."
        )
        settings.user_agent = DEFAULT_USER_AGENT
    ensure_directories(settings)

    repository = JobRepository(settings.db_path)
    repository.init_db()

    snapshots = RawSnapshotStore(settings.raw_dir)
    profiles = load_profiles(config_path)

    return RuntimeContext(
        settings=settings,
        profiles=profiles,
        repository=repository,
        snapshots=snapshots,
    )


class JobFinderService:
    def __init__(self, runtime: RuntimeContext) -> None:
        self.runtime = runtime

    def run(self, profile_id: str, crawl_only: bool = False) -> RunResult:
        profile = self._get_profile(profile_id)

        deps = WorkflowDependencies(
            adapters=build_adapters(profile),
            repository=self.runtime.repository,
            snapshots=self.runtime.snapshots,
            vector_index=SemanticVectorIndex(
                vector_dir=self.runtime.settings.vector_dir,
                base_url=self.runtime.settings.ollama_base_url,
                embed_model=self.runtime.settings.ollama_embed_model,
            ),
            llm_scorer=OllamaFitScorer(
                base_url=self.runtime.settings.ollama_base_url,
                model=self.runtime.settings.ollama_chat_model,
            ),
            report_dir=self.runtime.settings.report_dir,
            request_timeout_seconds=self.runtime.settings.request_timeout_seconds,
            user_agent=self.runtime.settings.user_agent,
        )

        workflow = JobFinderWorkflow(deps)
        return workflow.run(profile, crawl_only=crawl_only)

    def generate_report(self, profile_id: str, run_id: str | None = None, top_n: int | None = None) -> tuple[Path, Path]:
        profile = self._get_profile(profile_id)
        target_run = self.runtime.repository.get_run(run_id) if run_id else self.runtime.repository.get_latest_run_for_profile(profile_id)
        if target_run is None:
            raise RuntimeError("No run found for report generation")

        statuses = [
            SourceRunStatus(
                source=row.source,
                status=SourceStatus(row.status),
                fetched_count=row.fetched_count,
                normalized_count=row.normalized_count,
                error=row.error,
            )
            for row in self.runtime.repository.get_source_statuses(target_run.id)
        ]

        rows = self.runtime.repository.get_ranked_jobs(target_run.id, limit=top_n or profile.digest_size)
        ranked: list[RankedJob] = []
        for row in rows:
            job = NormalizedJobPosting(
                source=str(row["source"]),
                company=str(row["company"]),
                source_job_id=str(row["job_id"]),
                url=str(row["url"]),
                title=str(row["title"]),
                location_text=str(row["location_text"]),
                is_remote=bool(row["is_remote"]),
                posted_at=None,
                description_text="",
                employment_type=None,
                seniority=None,
                raw_snapshot_id="reconstructed",
                content_hash="reconstructed",
            )
            score = ScoreBreakdown(
                rule=float(row["rule_score"]),
                semantic=float(row["semantic_score"]),
                llm=float(row["llm_score"]),
                total=float(row["total_score"]),
                rationale=str(row["rationale"]),
            )
            ranked.append(
                RankedJob(
                    job=job,
                    score=score,
                    llm_fit=LLMFit(reasoning=str(row["llm_reasoning"])),
                    is_new_alert=bool(row["is_new_alert"]),
                )
            )

        run_result = RunResult(
            run_id=target_run.id,
            profile_id=target_run.profile_id,
            started_at=target_run.started_at,
            completed_at=target_run.completed_at,
            source_statuses=statuses,
            total_normalized_jobs=sum(s.normalized_count for s in statuses),
            total_ranked_jobs=len(ranked),
            top_jobs=ranked,
        )

        return write_run_reports(
            report_dir=self.runtime.settings.report_dir,
            run_result=run_result,
            ranked_jobs=ranked,
            top_n=top_n or profile.digest_size,
        )

    def prune(self, days: int | None = None) -> dict[str, int]:
        cutoff = days or self.runtime.settings.retention_days
        db_stats = self.runtime.repository.prune(cutoff)
        snapshot_deleted = self.runtime.snapshots.prune(cutoff)
        report_deleted = prune_report_files(self.runtime.settings.report_dir, cutoff)
        return {
            **db_stats,
            "raw_snapshots": snapshot_deleted,
            "reports": report_deleted,
        }

    def _get_profile(self, profile_id: str):
        profile = self.runtime.profiles.get(profile_id)
        if profile is None:
            known = ", ".join(sorted(self.runtime.profiles.keys()))
            raise RuntimeError(f"Unknown profile '{profile_id}'. Known profiles: {known}")
        return profile


def prune_report_files(report_dir: Path, retention_days: int) -> int:
    cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
    removed = 0
    for file in report_dir.rglob("*.md"):
        if file.stat().st_mtime < cutoff:
            file.unlink(missing_ok=True)
            removed += 1
    for file in report_dir.rglob("*.json"):
        if file.stat().st_mtime < cutoff:
            file.unlink(missing_ok=True)
            removed += 1
    return removed
