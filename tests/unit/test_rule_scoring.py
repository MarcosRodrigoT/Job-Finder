from jobfinder.models.domain import NormalizedJobPosting, SearchProfile
from jobfinder.scoring.rules import rule_score_job


def test_rule_score_hits_role_and_location() -> None:
    profile = SearchProfile(
        profile_id="test",
        target_roles=["Machine Learning Engineer"],
        role_synonyms=["Applied Scientist"],
        required_skills=["python", "deep learning"],
    )
    job = NormalizedJobPosting(
        source="x",
        company="Example",
        source_job_id="1",
        url="https://example.com/1",
        title="Senior Machine Learning Engineer",
        location_text="Madrid, Spain",
        is_remote=False,
        description_text="Python and deep learning experience required",
        raw_snapshot_id="raw1",
        content_hash="hash1",
    )

    score, rationale = rule_score_job(job, profile)
    assert score > 50
    assert "location matches Madrid" in rationale
