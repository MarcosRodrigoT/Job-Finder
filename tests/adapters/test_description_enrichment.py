import httpx

from jobfinder.adapters.linkedin_public import LinkedInPublicAdapter
from jobfinder.models.domain import SearchProfile


def test_linkedin_fetch_enriches_description_from_detail_page() -> None:
    adapter = LinkedInPublicAdapter()

    listing_html = """
    <ul>
      <li data-entity-urn="urn:li:jobPosting:12345">
        <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/12345/">AI Engineer</a>
        <h3>AI Engineer</h3>
        <h4>ExampleCo</h4>
        <span class="job-search-card__location">Madrid, Spain</span>
        <time datetime="2026-03-01">1 day ago</time>
      </li>
    </ul>
    """

    detail_html = """
    <html>
      <body>
        <div class="show-more-less-html__markup">
          <p>Build production ML systems.</p>
          <p>Work with applied research teams.</p>
        </div>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "seeMoreJobPostings/search" in url:
            return httpx.Response(200, text=listing_html)
        if "/jobs/view/12345/" in url:
            return httpx.Response(200, text=detail_html)
        return httpx.Response(404, text="not found")

    profile = SearchProfile(
        profile_id="madrid_ml",
        target_roles=["Machine Learning Engineer"],
        role_synonyms=["AI Engineer"],
    )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        jobs = adapter.fetch(profile, client)
    finally:
        client.close()

    assert len(jobs) == 1
    desc = jobs[0].payload.get("description", "")
    assert "Build production ML systems." in desc
    assert "applied research" in desc


def test_extract_description_helper_prefers_selector_html() -> None:
    adapter = LinkedInPublicAdapter()
    html = """
    <html>
      <body>
        <section class="job-content">
          <div class="show-more-less-html__markup"><p>Hello <strong>world</strong></p></div>
        </section>
      </body>
    </html>
    """

    desc = adapter._extract_description_from_html(html, selectors=["div.show-more-less-html__markup"])
    assert "<strong>world</strong>" in desc
