from jobfinder.adapters.apple import AppleJobsAdapter


def test_apple_candidate_job_url_filter() -> None:
    adapter = AppleJobsAdapter()

    assert adapter._is_candidate_job_url(
        "https://jobs.apple.com/en-us/details/200607049/machine-learning-engineer-global-siri"
    )
    assert not adapter._is_candidate_job_url("https://jobs.apple.com/en-us/search?search=machine+learning")
    assert not adapter._is_candidate_job_url(
        "https://jobs.apple.com/careers/choose-country-region.html"
    )
    assert not adapter._is_candidate_job_url(
        "https://jobs.apple.com/en-us/details/114438048/es-expert/locationPicker"
    )


def test_apple_extract_description_from_json_blob_prefers_job_description() -> None:
    adapter = AppleJobsAdapter()
    payload = {
        "props": {
            "pageProps": {
                "jobPosting": {
                    "jobDescription": "<p>Build ML systems for Siri understanding and ranking.</p>"
                },
                "chrome": {
                    "footer": "Apple Footer Privacy Policy Terms of Use Site Map"
                },
            }
        }
    }

    desc = adapter._extract_description_from_json_blob(payload)

    assert "Build ML systems" in desc
    assert "Apple Footer" not in desc
