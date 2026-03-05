from __future__ import annotations

from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from jobfinder.adapters.base import SourceAdapter, SourceBlockedError
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class LinkedInPublicAdapter(SourceAdapter):
    source = "linkedin"
    company = "LinkedIn"

    BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        params = {
            "keywords": " OR ".join(profile.role_terms()),
            "location": "Madrid, Community of Madrid, Spain",
            "start": 0,
        }
        url = f"{self.BASE_URL}?{urlencode(params)}"
        response = client.get(url)

        if response.status_code in {429, 999}:
            raise SourceBlockedError(f"LinkedIn blocked request with status {response.status_code}")

        body_lower = response.text.lower()
        if "captcha" in body_lower or "unusual traffic" in body_lower:
            raise SourceBlockedError("LinkedIn blocked request due to captcha")

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("li")
        results: list[RawJobPosting] = []
        for card in cards:
            link = card.select_one("a.base-card__full-link")
            title_tag = card.select_one("h3")
            company_tag = card.select_one("h4")
            location_tag = card.select_one("span.job-search-card__location")
            date_tag = card.select_one("time")
            if not link or not title_tag:
                continue
            payload = {
                "id": card.get("data-entity-urn", "").split(":")[-1] or link.get("href", ""),
                "title": title_tag.get_text(strip=True),
                "company": company_tag.get_text(strip=True) if company_tag else self.company,
                "location": location_tag.get_text(strip=True) if location_tag else "",
                "url": link.get("href", ""),
                "posted_at": date_tag.get("datetime") if date_tag else None,
                "description": "",
            }
            payload["description"] = self._fetch_job_description(client, payload["url"])
            results.append(RawJobPosting(source=self.source, company=payload["company"], payload=payload, url=payload["url"]))
        return results

    def _fetch_job_description(self, client: httpx.Client, url: str) -> str:
        if not url:
            return ""
        try:
            response = client.get(url)
        except httpx.HTTPError:
            return ""
        if response.status_code >= 400:
            return ""

        desc = self._extract_description_from_html(
            response.text,
            selectors=[
                "div.show-more-less-html__markup",
                "section.show-more-less-html",
                "div.description__text",
                "div.jobs-description-content__text",
                "div.jobs-box__html-content",
                "div.decorated-job-posting__details",
                "section.description",
            ],
        )
        # If selectors returned only boilerplate (very short), discard
        if desc and len(desc.split()) < 5:
            return ""
        return desc

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        payload = raw.payload
        location_text = payload.get("location", "")
        return NormalizedJobPosting(
            source=self.source,
            company=payload.get("company", self.company),
            source_job_id=str(payload.get("id", payload.get("url", ""))),
            url=payload.get("url") or "https://www.linkedin.com/jobs/",
            title=payload.get("title", "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(payload.get("posted_at")),
            description_text=payload.get("description", ""),
            employment_type=None,
            seniority=None,
            raw_snapshot_id="",
            content_hash=self._content_hash(payload),
        )
