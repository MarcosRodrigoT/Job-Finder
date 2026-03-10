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


def build_job_with_details(
    source_job_id: str,
    content_hash: str,
    company: str = "Mistral AI",
    title: str = "Machine Learning Engineer",
    description: str = "ML role",
) -> NormalizedJobPosting:
    return NormalizedJobPosting(
        source="lever_mistral",
        company=company,
        source_job_id=source_job_id,
        url=f"https://jobs.example/{source_job_id}",
        title=title,
        location_text="Madrid, Spain",
        is_remote=False,
        description_text=description,
        raw_snapshot_id=f"raw-{source_job_id}",
        content_hash=content_hash,
    )


def test_content_similar_repost_suppresses_alert(tmp_path: Path) -> None:
    """A reposted job with new ID but near-identical description should not trigger alert."""
    repo = JobRepository(tmp_path / "test.sqlite")
    repo.init_db()
    repo.start_run("run-1", "test")

    description = "We are looking for a senior ML engineer to join our team. " * 20
    original = build_job_with_details("orig-1", "hash-orig", description=description)
    mapping1 = repo.upsert_jobs("run-1", [original], dedup_days=90)
    assert next(iter(mapping1.values()))[1] is True  # is_new_alert

    # Same company, different source_job_id, nearly identical description
    repost = build_job_with_details("repost-1", "hash-repost", description=description)
    mapping2 = repo.upsert_jobs("run-1", [repost], dedup_days=90)
    assert next(iter(mapping2.values()))[1] is False  # suppressed


def test_different_content_same_company_triggers_alert(tmp_path: Path) -> None:
    """Different job at same company should still trigger alert."""
    repo = JobRepository(tmp_path / "test.sqlite")
    repo.init_db()
    repo.start_run("run-1", "test")

    desc_a = "Senior ML engineer role focused on computer vision and model training. " * 20
    desc_b = "Frontend developer role building React dashboards for analytics. " * 20

    job_a = build_job_with_details("job-a", "hash-a", description=desc_a)
    mapping1 = repo.upsert_jobs("run-1", [job_a], dedup_days=90)
    assert next(iter(mapping1.values()))[1] is True

    job_b = build_job_with_details("job-b", "hash-b", description=desc_b)
    mapping2 = repo.upsert_jobs("run-1", [job_b], dedup_days=90)
    assert next(iter(mapping2.values()))[1] is True  # genuinely different
