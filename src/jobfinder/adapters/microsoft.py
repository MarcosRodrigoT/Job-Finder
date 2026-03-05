from __future__ import annotations

from urllib.parse import urlencode

import httpx

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import RawJobPosting, SearchProfile


class MicrosoftCareersAdapter(GenericPublicCareersAdapter):
    source = "microsoft"
    company = "Microsoft"

    ROOT_URL = "https://apply.careers.microsoft.com/careers"
    API_URL = "https://gcsservices.careers.microsoft.com/search/api/v1/search"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = (
        "apply.careers.microsoft.com",
        "careers.microsoft.com",
        "jobs.careers.microsoft.com",
    )
    WAIT_SELECTOR = "a[href*='/careers/job/']"
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        params = {
            "query": self._keyword_query(profile),
            "location": self._location_query(profile),
            "sort_by": "relevance",
            "filter_include_remote": 1,
        }
        return [f"{self.ROOT_URL}?{urlencode(params)}"]

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        api_jobs: list[dict[str, str | None]] = []

        try:
            params = {
                "l": "en_us",
                "q": self._keyword_query(profile),
                "lc": self._location_query(profile),
                "pg": 1,
                "pgSz": 100,
                "o": "Relevance",
                "flt": "true",
            }
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
        def find_job_lists(node: object) -> list[list[dict[str, object]]]:
            found: list[list[dict[str, object]]] = []
            if isinstance(node, dict):
                for value in node.values():
                    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                        sample = value[0]
                        if isinstance(sample, dict) and ("title" in sample or "jobTitle" in sample or "properties" in sample):
                            found.append([item for item in value if isinstance(item, dict)])
                    else:
                        found.extend(find_job_lists(value))
            elif isinstance(node, list):
                for item in node:
                    found.extend(find_job_lists(item))
            return found

        job_lists = find_job_lists(payload)
        if not job_lists:
            return []

        candidates = max(job_lists, key=len)
        jobs: list[dict[str, str | None]] = []
        for item in candidates:
            title = str(item.get("title") or item.get("jobTitle") or "").strip()
            if not title:
                continue

            url = str(
                item.get("url")
                or item.get("applyUrl")
                or item.get("jobPostingUrl")
                or ""
            ).strip()
            if not url:
                item_id = str(item.get("jobId") or item.get("id") or "").strip()
                if item_id:
                    url = f"{self.ROOT_URL}/job/{item_id}"
            if not url:
                continue

            location = str(item.get("location") or item.get("primaryLocation") or "").strip()
            if not location:
                properties = item.get("properties")
                if isinstance(properties, dict):
                    location = str(properties.get("primaryLocation") or properties.get("location") or "").strip()

            jobs.append(
                {
                    "id": str(item.get("jobId") or item.get("id") or url),
                    "title": title,
                    "location": location,
                    "url": url,
                    "posted_at": str(item.get("postingDate") or item.get("postedDate") or "") or None,
                    "description": str(item.get("description") or "") or None,
                }
            )

        return jobs


__all__ = ["MicrosoftCareersAdapter"]
