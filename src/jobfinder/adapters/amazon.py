from __future__ import annotations

from urllib.parse import urlencode

import httpx

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import RawJobPosting, SearchProfile


class AmazonJobsAdapter(GenericPublicCareersAdapter):
    source = "amazon"
    company = "Amazon"

    SEARCH_ROOT = "https://www.amazon.jobs/en/search"
    API_URL = "https://www.amazon.jobs/en/search.json"

    SEARCH_URLS = (SEARCH_ROOT,)
    ALLOWED_DOMAINS = ("amazon.jobs", "www.amazon.jobs")
    DESCRIPTION_SELECTORS = (
        "div.job-detail-body",
        "div.section.description",
        "section.job-detail",
        "main",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        params = {
            "base_query": self._keyword_query(profile),
            "loc_query": self._location_query(profile),
            "country": "ESP",
        }
        return [f"{self.SEARCH_ROOT}?{urlencode(params)}"]

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        params = {
            "base_query": self._keyword_query(profile),
            "loc_query": self._location_query(profile),
            "country": "ESP",
        }

        api_jobs: list[dict[str, str | None]] = []
        try:
            response = client.get(self.API_URL, params=params)
            if response.status_code == 200:
                payload = response.json()
                api_jobs = self._extract_api_jobs(payload)
        except Exception:
            api_jobs = []

        if api_jobs:
            return self._to_raw_postings(api_jobs, client)

        return super().fetch(profile, client, browser_ctx=browser_ctx)

    def _extract_api_jobs(self, payload: object) -> list[dict[str, str | None]]:
        if not isinstance(payload, dict):
            return []

        candidates: list[dict[str, object]] = []
        for key in ("jobs", "results", "search_results", "job_search_results"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend([item for item in value if isinstance(item, dict)])

        jobs: list[dict[str, str | None]] = []
        for item in candidates:
            title = str(item.get("title") or item.get("job_title") or "").strip()
            if not title:
                continue

            job_path = str(item.get("job_path") or item.get("job_pathname") or "").strip()
            absolute = str(item.get("absolute_url") or item.get("url") or "").strip()
            url = absolute
            if not url and job_path:
                url = f"https://www.amazon.jobs{job_path}"
            if not url:
                continue

            location = (
                str(item.get("location") or "").strip()
                or str(item.get("city") or "").strip()
                or str(item.get("location_name") or "").strip()
            )

            jobs.append(
                {
                    "id": str(item.get("id") or item.get("job_id") or url),
                    "title": title,
                    "location": location,
                    "url": url,
                    "posted_at": str(item.get("updated_at") or item.get("posted_date") or "") or None,
                    "description": str(item.get("description") or item.get("description_html") or "") or None,
                }
            )

        return jobs


__all__ = ["AmazonJobsAdapter"]
