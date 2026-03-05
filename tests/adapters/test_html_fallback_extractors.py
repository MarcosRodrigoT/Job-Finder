from jobfinder.adapters.openai import OpenAIAdapter
from jobfinder.adapters.workable import WorkableAdapter


def test_openai_extract_jobs_from_json_ld_and_links() -> None:
    adapter = OpenAIAdapter()
    html = """
    <html>
      <head>
        <script type='application/ld+json'>
          {
            "@type": "JobPosting",
            "title": "Applied Research Engineer",
            "url": "https://openai.com/careers/job-123",
            "datePosted": "2026-03-01"
          }
        </script>
      </head>
      <body>
        <a href="/careers/job-456">Machine Learning Engineer</a>
      </body>
    </html>
    """

    jobs = adapter._extract_jobs_from_html(html, base_url="https://openai.com")

    urls = {str(job["url"]) for job in jobs}
    assert "https://openai.com/careers/job-123" in urls
    assert "https://openai.com/careers/job-456" in urls


def test_openai_ashby_api_parser() -> None:
    adapter = OpenAIAdapter()
    # Simulate the Ashby API JSON structure
    import json
    import httpx

    ashby_response = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Applied Research Scientist",
                "department": "Research",
                "team": "Research",
                "employmentType": "FullTime",
                "location": "San Francisco",
                "secondaryLocations": [{"location": "New York", "address": {"postalAddress": {}}}],
                "descriptionPlain": "We are looking for an Applied Research Scientist.",
                "publishedAt": "2026-03-01T10:00:00Z",
                "isListed": True,
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ashby_response)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        jobs = adapter._fetch_from_ashby_api(client)
    finally:
        client.close()

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Applied Research Scientist"
    assert jobs[0]["location"] == "San Francisco, New York"
    assert jobs[0]["url"] == "https://jobs.ashbyhq.com/openai/abc-123"
    assert jobs[0]["description"] == "We are looking for an Applied Research Scientist."


def test_workable_api_payload_parser() -> None:
    adapter = WorkableAdapter()

    api_jobs = [
        {
            "shortcode": "ABC123",
            "title": "ML Engineer",
            "remote": True,
            "location": {
                "country": "France",
                "city": "Paris",
                "region": "Ile-de-France",
            },
            "locations": [
                {"country": "France", "city": "Paris"},
                {"country": "Spain", "city": "Madrid"},
            ],
            "published": "2026-03-01T10:00:00Z",
            "description": "ML role description",
            "type": "Full-time",
        }
    ]

    postings = adapter._from_api_payload(api_jobs)

    assert len(postings) == 1
    p = postings[0]
    assert p.payload["title"] == "ML Engineer"
    assert "Paris" in p.payload["location"]
    assert "Madrid" in p.payload["location"]
    assert "Remote" in p.payload["location"]
    assert p.payload["url"] == "https://apply.workable.com/huggingface/j/ABC123/"
