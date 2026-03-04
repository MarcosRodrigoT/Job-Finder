from pathlib import Path

from jobfinder.models.domain import NormalizedJobPosting
from jobfinder.storage.repository import JobRepository


def build_job(content_hash: str) -> NormalizedJobPosting:
    return NormalizedJobPosting(
        source="lever_mistral",
        company="Mistral AI",
        source_job_id="abc123",
        url="https://jobs.example/abc123",
        title="Machine Learning Engineer",
        location_text="Madrid, Spain",
        is_remote=False,
        description_text="ML role",
        raw_snapshot_id="raw-1",
        content_hash=content_hash,
    )


def test_upsert_dedup_alert_window(tmp_path: Path) -> None:
    repo = JobRepository(tmp_path / "test.sqlite")
    repo.init_db()
    repo.start_run("run-1", "test")

    mapping1 = repo.upsert_jobs("run-1", [build_job("hash-a")], dedup_days=90)
    assert mapping1

    mapping2 = repo.upsert_jobs("run-1", [build_job("hash-a")], dedup_days=90)
    assert mapping2

    first = next(iter(mapping1.values()))
    second = next(iter(mapping2.values()))
    assert first[0] == second[0]
    assert first[1] is True
    assert second[1] is False
