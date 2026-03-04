import httpx

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


def test_openai_greenhouse_payload_parser() -> None:
    adapter = OpenAIAdapter()
    payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Applied Research Scientist",
                "absolute_url": "https://boards.greenhouse.io/openai/jobs/101",
                "location": {"name": "San Francisco, CA"},
                "updated_at": "2026-03-01T10:00:00Z",
                "content": "<p>Research role</p>",
            }
        ]
    }

    jobs = adapter._extract_jobs_from_greenhouse_payload(payload)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Applied Research Scientist"
    assert jobs[0]["location"] == "San Francisco, CA"


def test_workable_html_fallback_extracts_job_links() -> None:
    adapter = WorkableAdapter()

    html = """
    <html>
      <body>
        <div>
          <a href="/j/ABC123">ML Engineer</a>
          <span>Madrid, Spain</span>
        </div>
        <div>
          <a href="https://apply.workable.com/huggingface/j/XYZ987">Applied Scientist</a>
          <span>Remote</span>
        </div>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        jobs = adapter._from_public_html(client)
    finally:
        client.close()

    assert len(jobs) == 2
    assert jobs[0].payload["title"]
    assert str(jobs[0].payload["url"]).startswith("http")
