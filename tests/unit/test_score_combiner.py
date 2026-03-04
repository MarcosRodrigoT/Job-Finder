from jobfinder.models.domain import ScoringWeights
from jobfinder.scoring.combine import combine_scores


def test_score_combiner_uses_weights() -> None:
    weights = ScoringWeights(rule=0.35, semantic=0.30, llm=0.35)
    score = combine_scores(80, 60, 50, weights, rationale="test")

    assert score.total == 63.5
    assert score.rule == 80
    assert score.semantic == 60
    assert score.llm == 50
