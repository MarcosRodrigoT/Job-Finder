from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class AnthropicAdapter(SourceAdapter):
    source = "anthropic"
    company = "Anthropic"

    SEARCH_URL = "https://www.anthropic.com/careers/jobs"

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        response = client.get(self.SEARCH_URL)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        out: list[RawJobPosting] = []
        seen_urls: set[str] = set()
        for anchor in soup.select("a[href*='/jobs/']"):
            title = anchor.get_text(strip=True)
            href = anchor.get("href", "")
            if not title or not href:
                continue
            url = href if href.startswith("http") else f"https://www.anthropic.com{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            description = self._fetch_job_description(client, url)
            out.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": href,
                        "title": title,
                        "location": "",
                        "url": url,
                        "posted_at": None,
                        "description": description,
                    },
                    url=href,
                )
            )
        return out

    def _fetch_job_description(self, client: httpx.Client, url: str) -> str:
        if not url:
            return ""
        try:
            response = client.get(url)
        except httpx.HTTPError:
            return ""
        if response.status_code >= 400:
            return ""

        return self._extract_description_from_html(
            response.text,
            selectors=[
                "section[data-testid='job-description']",
                "div[data-testid='job-description']",
                "div[class*='job-description']",
                "section[class*='job-description']",
                "article",
            ],
        )

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = p.get("location", "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id", p.get("url", ""))),
            url=p.get("url") or self.SEARCH_URL,
            title=p.get("title", "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(p.get("posted_at")),
            description_text=p.get("description", ""),
            employment_type=None,
            seniority=None,
            raw_snapshot_id="",
            content_hash=self._content_hash(p),
        )
