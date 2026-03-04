from pathlib import Path

from jobfinder.adapters.base import SourceAdapter, SourceBlockedError
from jobfinder.graph.workflow import JobFinderWorkflow, WorkflowDependencies
from jobfinder.models.domain import LLMFit, NormalizedJobPosting, RawJobPosting, SearchProfile
from jobfinder.scoring.llm import OllamaFitScorer
from jobfinder.storage import JobRepository, RawSnapshotStore, SemanticVectorIndex


class DummyAdapter(SourceAdapter):
    source = "dummy"
    company = "DummyCo"

    def fetch(self, profile, client, browser_ctx=None):
        return [
            RawJobPosting(
                source=self.source,
                company=self.company,
                payload={
                    "id": "1",
                    "title": "Machine Learning Engineer",
                    "location": "Madrid, Spain",
                    "url": "https://dummy/jobs/1",
                    "posted_at": "2026-03-01T00:00:00Z",
                    "description": "Python and ML",
                },
            )
        ]

    def normalize(self, raw):
        p = raw.payload
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=p["id"],
            url=p["url"],
            title=p["title"],
            location_text=p["location"],
            description_text=p["description"],
            raw_snapshot_id="",
            content_hash=self._content_hash(p),
        )


class BlockedLinkedInAdapter(SourceAdapter):
    source = "linkedin"
    company = "LinkedIn"

    def fetch(self, profile, client, browser_ctx=None):
        raise SourceBlockedError("captcha")

    def normalize(self, raw):
        raise NotImplementedError


class StubSemanticIndex(SemanticVectorIndex):
    def __init__(self, vector_dir: Path):
        self.vector_dir = vector_dir
        self.vector_dir.mkdir(parents=True, exist_ok=True)

    def score_jobs(self, run_id, profile, jobs):
        return {job.fingerprint(): 60.0 for job in jobs}


class StubLLMScorer(OllamaFitScorer):
    def __init__(self):
        pass

    def score_job(self, profile, job):
        return LLMFit(
            role_fit=8.0,
            research_fit=7.0,
            location_fit=9.0,
            seniority_fit=7.0,
            reasoning="strong role and location match",
        )


def test_pipeline_runs_with_blocked_linkedin(tmp_path: Path) -> None:
    repo = JobRepository(tmp_path / "db.sqlite")
    repo.init_db()

    deps = WorkflowDependencies(
        adapters=[BlockedLinkedInAdapter(), DummyAdapter()],
        repository=repo,
        snapshots=RawSnapshotStore(tmp_path / "raw"),
        vector_index=StubSemanticIndex(tmp_path / "vec"),
        llm_scorer=StubLLMScorer(),
        report_dir=tmp_path / "reports",
        request_timeout_seconds=5.0,
        user_agent="test-agent",
    )
    workflow = JobFinderWorkflow(deps)

    profile = SearchProfile(
        profile_id="madrid_ml",
        target_roles=["Machine Learning Engineer"],
        role_synonyms=["Applied Research"],
        required_skills=["python"],
        locations=["Madrid", "Spain"],
    )

    result = workflow.run(profile=profile)

    assert result.total_normalized_jobs == 1
    assert result.total_ranked_jobs >= 1
    assert any("LinkedIn appears blocked" in msg for msg in result.warnings)
    assert result.report_markdown_path is not None
    assert result.report_json_path is not None
