import httpx

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.adapters.microsoft import MicrosoftCareersAdapter
from jobfinder.models.domain import SearchProfile


class DummyGenericAdapter(GenericPublicCareersAdapter):
    source = "dummy_generic"
    company = "DummyCo"
    SEARCH_URLS = ("https://example.com/careers",)
    ALLOWED_DOMAINS = ("example.com",)


def test_generic_adapter_extracts_json_ld_and_anchor_jobs() -> None:
    adapter = DummyGenericAdapter()
    html = """
    <html>
      <head>
        <script type='application/ld+json'>
          {
            "@graph": [
              {
                "@type": "JobPosting",
                "title": "Applied Research Engineer",
                "url": "https://example.com/jobs/123",
                "datePosted": "2026-03-01"
              }
            ]
          }
        </script>
      </head>
      <body>
        <a href="/careers/jobs/456">Machine Learning Engineer</a>
      </body>
    </html>
    """

    profile = SearchProfile(
        profile_id="madrid_ml",
        target_roles=["Machine Learning Engineer"],
        role_synonyms=["Applied Research"],
        locations=["Madrid", "Spain"],
    )

    jobs = adapter._extract_jobs(html, "https://example.com/careers", profile)
    urls = {str(job["url"]) for job in jobs}

    assert "https://example.com/jobs/123" in urls
    assert "https://example.com/careers/jobs/456" in urls


def test_generic_adapter_fetch_enriches_description() -> None:
    adapter = DummyGenericAdapter()

    listing_html = """
    <html><body>
      <a href="/jobs/123">AI Engineer</a>
    </body></html>
    """

    detail_html = """
    <html><body>
      <div class="job-description"><p>Build ML systems at scale.</p></div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://example.com/careers"):
            return httpx.Response(200, text=listing_html)
        if url.startswith("https://example.com/jobs/123"):
            return httpx.Response(200, text=detail_html)
        return httpx.Response(404, text="not found")

    profile = SearchProfile(profile_id="madrid_ml", target_roles=["AI Engineer"], locations=["Spain"])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        jobs = adapter.fetch(profile, client)
    finally:
        client.close()

    assert len(jobs) == 1
    assert "Build ML systems" in str(jobs[0].payload.get("description") or "")


def test_microsoft_api_parser_finds_jobs_in_nested_payload() -> None:
    adapter = MicrosoftCareersAdapter()
    payload = {
        "operationResult": {
            "result": {
                "jobs": [
                    {
                        "jobId": "A-100",
                        "title": "Applied Scientist",
                        "primaryLocation": "Madrid, Spain",
                        "url": "https://apply.careers.microsoft.com/careers/job/A-100",
                    }
                ]
            }
        }
    }

    jobs = adapter._extract_api_jobs(payload)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "A-100"
    assert "microsoft.com" in str(jobs[0]["url"])
