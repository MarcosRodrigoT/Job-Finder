from unittest.mock import MagicMock

from jobfinder.models.domain import NormalizedJobPosting, SearchProfile
from jobfinder.scoring.llm import OllamaFitScorer


def _make_profile(summary: str = "") -> SearchProfile:
    return SearchProfile(
        profile_id="test",
        target_roles=["MLE"],
        candidate_summary=summary,
    )


def _make_job() -> NormalizedJobPosting:
    return NormalizedJobPosting(
        source="test",
        company="Acme",
        source_job_id="j1",
        url="https://example.com/j1",
        title="ML Engineer",
        location_text="Madrid",
        description_text="Train models with PyTorch.",
        raw_snapshot_id="raw-1",
        content_hash="hash-1",
    )


def test_coerce_nested_reasoning_payload() -> None:
    scorer = OllamaFitScorer.__new__(OllamaFitScorer)

    parsed = {
        "reasoning": {
            "role_fit": "8/10",
            "research_fit": "7",
            "location_fit": "9",
            "seniority_fit": "6",
            "summary": "Strong role and location match",
        }
    }

    coerced = scorer._coerce_fit_payload(parsed)

    assert coerced["role_fit"] == 8.0
    assert coerced["research_fit"] == 7.0
    assert coerced["location_fit"] == 9.0
    assert coerced["seniority_fit"] == 6.0
    assert isinstance(coerced["reasoning"], str)


def test_parse_score_supports_ratio_and_percentage() -> None:
    scorer = OllamaFitScorer.__new__(OllamaFitScorer)

    assert scorer._parse_score("9/10") == 9.0
    assert scorer._parse_score("80") == 8.0
    assert scorer._parse_score("not available") == 0.0


def test_score_job_includes_candidate_summary_in_prompt() -> None:
    scorer = OllamaFitScorer.__new__(OllamaFitScorer)
    scorer.llm = MagicMock()
    scorer.llm.invoke.return_value = MagicMock(
        content='{"role_fit":8,"research_fit":7,"location_fit":9,"seniority_fit":6,"reasoning":"good"}'
    )

    profile = _make_profile("I want to train models.")
    job = _make_job()
    scorer.score_job(profile, job)

    call_args = scorer.llm.invoke.call_args[0][0]
    human_content = call_args[1].content
    assert "candidate_summary" in human_content
    assert "I want to train models." in human_content


def test_score_job_omits_candidate_summary_when_empty() -> None:
    scorer = OllamaFitScorer.__new__(OllamaFitScorer)
    scorer.llm = MagicMock()
    scorer.llm.invoke.return_value = MagicMock(
        content='{"role_fit":8,"research_fit":7,"location_fit":9,"seniority_fit":6,"reasoning":"good"}'
    )

    profile = _make_profile("")
    job = _make_job()
    scorer.score_job(profile, job)

    call_args = scorer.llm.invoke.call_args[0][0]
    human_content = call_args[1].content
    assert "candidate_summary" not in human_content
