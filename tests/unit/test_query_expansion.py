from jobfinder.models.domain import SearchProfile


def test_role_terms_deduplicated() -> None:
    profile = SearchProfile(
        profile_id="test",
        target_roles=["Machine Learning Engineer", "Applied Research"],
        role_synonyms=["Applied Research", "Research Engineer"],
    )

    terms = profile.role_terms()
    assert terms == ["Machine Learning Engineer", "Applied Research", "Research Engineer"]
