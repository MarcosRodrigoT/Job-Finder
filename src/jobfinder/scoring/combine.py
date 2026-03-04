from __future__ import annotations

from jobfinder.models.domain import ScoreBreakdown, ScoringWeights


def combine_scores(
    rule_score: float,
    semantic_score: float,
    llm_score: float,
    weights: ScoringWeights,
    rationale: str,
) -> ScoreBreakdown:
    total = (
        rule_score * weights.rule
        + semantic_score * weights.semantic
        + llm_score * weights.llm
    )
    return ScoreBreakdown(
        rule=round(rule_score, 2),
        semantic=round(semantic_score, 2),
        llm=round(llm_score, 2),
        total=round(max(0.0, min(100.0, total)), 2),
        rationale=rationale,
    )
