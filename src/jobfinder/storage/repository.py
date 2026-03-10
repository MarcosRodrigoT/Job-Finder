from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from sqlmodel import Session, SQLModel, create_engine, delete, select

from jobfinder.models.db import (
    AlertRecord,
    JobRecord,
    JobScoreRecord,
    JobVersionRecord,
    ProfileSnapshotRecord,
    RunRecord,
    RunSourceStatusRecord,
)
from jobfinder.models.domain import NormalizedJobPosting, RankedJob, SearchProfile, SourceRunStatus

logger = logging.getLogger(__name__)


class JobRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def start_run(self, run_id: str, profile_id: str) -> None:
        with Session(self.engine) as session:
            session.add(RunRecord(id=run_id, profile_id=profile_id))
            session.commit()

    def complete_run(self, run_id: str, status: str, warnings: int, errors: int) -> None:
        with Session(self.engine) as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return
            run.status = status
            run.completed_at = datetime.now(UTC)
            run.warning_count = warnings
            run.error_count = errors
            session.add(run)
            session.commit()

    def save_source_statuses(self, run_id: str, statuses: Iterable[SourceRunStatus]) -> None:
        with Session(self.engine) as session:
            for status in statuses:
                session.add(
                    RunSourceStatusRecord(
                        run_id=run_id,
                        source=status.source,
                        status=status.status.value,
                        fetched_count=status.fetched_count,
                        normalized_count=status.normalized_count,
                        error=status.error,
                    )
                )
            session.commit()

    def snapshot_profile(self, run_id: str, profile: SearchProfile) -> None:
        with Session(self.engine) as session:
            session.add(
                ProfileSnapshotRecord(
                    run_id=run_id,
                    profile_id=profile.profile_id,
                    payload_json=profile.model_dump_json(),
                )
            )
            session.commit()

    def _is_content_similar_to_recent(
        self,
        session: Session,
        item: NormalizedJobPosting,
        cutoff: datetime,
        threshold: float = 0.85,
    ) -> bool:
        """Check if a new job's description closely matches a recent job from same source+company."""
        similar_jobs_stmt = select(JobRecord).where(
            JobRecord.source == item.source,
            JobRecord.company == item.company,
            JobRecord.last_seen_at >= cutoff,
            JobRecord.source_job_id != item.source_job_id,
        )
        similar_jobs = session.exec(similar_jobs_stmt).all()
        if not similar_jobs:
            return False

        new_desc = re.sub(r"\s+", " ", item.description_text[:1000].lower().strip())
        if not new_desc:
            return False

        for existing_job in similar_jobs:
            version_stmt = select(JobVersionRecord).where(
                JobVersionRecord.job_id == existing_job.id,
            ).order_by(JobVersionRecord.created_at.desc())
            version = session.exec(version_stmt).first()
            if version is None or not version.description_text:
                continue
            existing_desc = re.sub(r"\s+", " ", version.description_text[:1000].lower().strip())
            ratio = SequenceMatcher(None, new_desc, existing_desc).ratio()
            if ratio >= threshold:
                return True

        return False

    def upsert_jobs(
        self,
        run_id: str,
        jobs: Iterable[NormalizedJobPosting],
        dedup_days: int,
    ) -> dict[str, tuple[int, bool]]:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=dedup_days)
        result: dict[str, tuple[int, bool]] = {}

        with Session(self.engine) as session:
            for item in jobs:
                statement = select(JobRecord).where(
                    JobRecord.source == item.source,
                    JobRecord.source_job_id == item.source_job_id,
                )
                job_rec = session.exec(statement).first()

                if job_rec is None:
                    job_rec_is_new = True
                    job_rec = JobRecord(
                        source=item.source,
                        company=item.company,
                        source_job_id=item.source_job_id,
                        url=str(item.url),
                        title=item.title,
                        location_text=item.location_text,
                        is_remote=item.is_remote,
                        latest_content_hash=item.content_hash,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    session.add(job_rec)
                    session.flush()
                else:
                    job_rec_is_new = False
                    job_rec.url = str(item.url)
                    job_rec.title = item.title
                    job_rec.location_text = item.location_text
                    job_rec.is_remote = item.is_remote
                    job_rec.last_seen_at = now
                    session.add(job_rec)

                if job_rec.latest_content_hash != item.content_hash:
                    job_rec.latest_content_hash = item.content_hash
                    session.add(job_rec)

                version_stmt = select(JobVersionRecord).where(
                    JobVersionRecord.job_id == job_rec.id,
                    JobVersionRecord.content_hash == item.content_hash,
                )
                existing_version = session.exec(version_stmt).first()
                if existing_version is None:
                    session.add(
                        JobVersionRecord(
                            job_id=job_rec.id,
                            run_id=run_id,
                            content_hash=item.content_hash,
                            raw_snapshot_id=item.raw_snapshot_id,
                            description_text=item.description_text,
                            employment_type=item.employment_type,
                            seniority=item.seniority,
                            posted_at=item.posted_at,
                        )
                    )

                if job_rec_is_new:
                    # New source_job_id: check if content-similar to recent job
                    content_similar = self._is_content_similar_to_recent(
                        session, item, cutoff,
                    )
                    is_new_alert = not content_similar
                    if content_similar:
                        logger.info(
                            "Suppressed alert for %s — content-similar to existing job at %s",
                            item.fingerprint(),
                            item.company,
                        )
                else:
                    # Existing job: check dedup window
                    recent_alert_stmt = select(AlertRecord).where(
                        AlertRecord.job_id == job_rec.id,
                        AlertRecord.created_at >= cutoff,
                    )
                    recent_alert = session.exec(recent_alert_stmt).first()
                    is_new_alert = recent_alert is None

                if is_new_alert:
                    session.add(AlertRecord(run_id=run_id, job_id=job_rec.id))

                result[item.fingerprint()] = (int(job_rec.id), is_new_alert)

            session.commit()

        return result

    def save_scores(self, run_id: str, ranked_jobs: Iterable[RankedJob], job_map: dict[str, tuple[int, bool]]) -> None:
        with Session(self.engine) as session:
            session.exec(delete(JobScoreRecord).where(JobScoreRecord.run_id == run_id))
            for ranked in ranked_jobs:
                fp = ranked.job.fingerprint()
                job_meta = job_map.get(fp)
                if job_meta is None:
                    continue
                job_id, is_new_alert = job_meta
                session.add(
                    JobScoreRecord(
                        run_id=run_id,
                        job_id=job_id,
                        rule_score=ranked.score.rule,
                        semantic_score=ranked.score.semantic,
                        llm_score=ranked.score.llm,
                        total_score=ranked.score.total,
                        rationale=ranked.score.rationale,
                        llm_reasoning=ranked.llm_fit.reasoning,
                        is_new_alert=is_new_alert,
                    )
                )
            session.commit()

    def get_latest_run(self) -> RunRecord | None:
        with Session(self.engine) as session:
            return session.exec(select(RunRecord).order_by(RunRecord.started_at.desc())).first()

    def get_latest_run_for_profile(self, profile_id: str) -> RunRecord | None:
        with Session(self.engine) as session:
            return session.exec(
                select(RunRecord)
                .where(RunRecord.profile_id == profile_id)
                .order_by(RunRecord.started_at.desc())
            ).first()

    def get_run(self, run_id: str) -> RunRecord | None:
        with Session(self.engine) as session:
            return session.get(RunRecord, run_id)

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with Session(self.engine) as session:
            rows = session.exec(select(RunRecord).order_by(RunRecord.started_at.desc()).limit(limit)).all()
            return list(rows)

    def get_source_statuses(self, run_id: str) -> list[RunSourceStatusRecord]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(RunSourceStatusRecord)
                .where(RunSourceStatusRecord.run_id == run_id)
                .order_by(RunSourceStatusRecord.source.asc())
            ).all()
            return list(rows)

    def get_ranked_jobs(self, run_id: str, limit: int = 100) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            score_rows = session.exec(
                select(JobScoreRecord)
                .where(JobScoreRecord.run_id == run_id)
                .order_by(JobScoreRecord.total_score.desc())
                .limit(limit)
            ).all()

            items: list[dict[str, object]] = []
            for score in score_rows:
                job = session.get(JobRecord, score.job_id)
                if job is None:
                    continue
                items.append(
                    {
                        "job_id": job.id,
                        "source": job.source,
                        "company": job.company,
                        "title": job.title,
                        "location_text": job.location_text,
                        "is_remote": job.is_remote,
                        "url": job.url,
                        "total_score": score.total_score,
                        "rule_score": score.rule_score,
                        "semantic_score": score.semantic_score,
                        "llm_score": score.llm_score,
                        "rationale": score.rationale,
                        "llm_reasoning": score.llm_reasoning,
                        "is_new_alert": score.is_new_alert,
                    }
                )
            return items

    def get_job(self, job_id: int) -> JobRecord | None:
        with Session(self.engine) as session:
            return session.get(JobRecord, job_id)

    def get_latest_job_version(self, job_id: int) -> JobVersionRecord | None:
        with Session(self.engine) as session:
            row = session.exec(
                select(JobVersionRecord)
                .where(JobVersionRecord.job_id == job_id)
                .order_by(JobVersionRecord.created_at.desc())
            ).first()
            return row

    def prune(self, older_than_days: int) -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        deleted = {"runs": 0, "run_source_status": 0, "job_scores": 0, "alerts": 0}
        with Session(self.engine) as session:
            old_runs = session.exec(select(RunRecord.id).where(RunRecord.started_at < cutoff)).all()
            old_run_ids = list(old_runs)
            if old_run_ids:
                result = session.exec(delete(RunSourceStatusRecord).where(RunSourceStatusRecord.run_id.in_(old_run_ids)))
                deleted["run_source_status"] = int(getattr(result, "rowcount", 0) or 0)
                result = session.exec(delete(JobScoreRecord).where(JobScoreRecord.run_id.in_(old_run_ids)))
                deleted["job_scores"] = int(getattr(result, "rowcount", 0) or 0)
                result = session.exec(delete(AlertRecord).where(AlertRecord.run_id.in_(old_run_ids)))
                deleted["alerts"] = int(getattr(result, "rowcount", 0) or 0)
                result = session.exec(delete(RunRecord).where(RunRecord.id.in_(old_run_ids)))
                deleted["runs"] = int(getattr(result, "rowcount", 0) or 0)
            session.commit()
        return deleted
