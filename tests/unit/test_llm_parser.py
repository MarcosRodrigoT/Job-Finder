from jobfinder.scoring.llm import OllamaFitScorer


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
