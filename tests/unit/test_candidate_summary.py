from jobfinder.models.domain import SearchProfile


def test_search_profile_candidate_summary_defaults_empty() -> None:
    profile = SearchProfile(profile_id="test", target_roles=["MLE"])
    assert profile.candidate_summary == ""


def test_search_profile_candidate_summary_from_yaml_data() -> None:
    data = {
        "profile_id": "test",
        "target_roles": ["MLE"],
        "candidate_summary": "I want to train models.",
    }
    profile = SearchProfile.model_validate(data)
    assert profile.candidate_summary == "I want to train models."
