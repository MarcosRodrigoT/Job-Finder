from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class AmazonJobsAdapter(SourceAdapter):
    source = "amazon"
    company = "Amazon"

    API_URL = "https://www.amazon.jobs/en/search.json"
    MAX_PAGES = 5
    PAGE_SIZE = 10

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        all_jobs = self._fetch_from_api(client, profile)
        return self._to_raw_postings(all_jobs)

    def _search_query(self, profile: SearchProfile) -> str:
        if profile.required_skills:
            return profile.required_skills[0]
        return "machine learning"

    def _country_code(self, profile: SearchProfile) -> str:
        for location in profile.locations:
            lowered = location.lower()
            if "spain" in lowered or "madrid" in lowered or "barcelona" in lowered:
                return "ESP"
        return ""

    def _fetch_from_api(self, client: httpx.Client, profile: SearchProfile) -> list[dict]:
        all_jobs: list[dict] = []
        base_query = self._search_query(profile)
        country = self._country_code(profile)

        for page in range(self.MAX_PAGES):
            params: dict[str, str | int] = {
                "base_query": base_query,
                "offset": page * self.PAGE_SIZE,
                "result_limit": self.PAGE_SIZE,
            }
            if country:
                params["country"] = country
            try:
                response = client.get(self.API_URL, params=params)
            except httpx.HTTPError:
                break

            if response.status_code != 200:
                break

            try:
                payload = response.json()
            except Exception:
                break

            if not isinstance(payload, dict):
                break

            jobs = payload.get("jobs", [])
            if not isinstance(jobs, list) or not jobs:
                break

            all_jobs.extend(j for j in jobs if isinstance(j, dict))

            hits = payload.get("hits", 0)
            if (page + 1) * self.PAGE_SIZE >= hits:
                break

        return all_jobs

    def _to_raw_postings(self, jobs: list[dict]) -> list[RawJobPosting]:
        postings: list[RawJobPosting] = []
        seen_urls: set[str] = set()

        for item in jobs:
            title = str(item.get("title") or item.get("job_title") or "").strip()
            if not title:
                continue

            job_path = str(item.get("job_path") or "").strip()
            url = ""
            if job_path:
                url = f"https://www.amazon.jobs{job_path}"
            if not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            location = str(item.get("location") or "").strip()
            if not location:
                city = str(item.get("city") or "").strip()
                country = str(item.get("country_code") or "").strip()
                location = ", ".join(p for p in [city, country] if p)

            description = str(item.get("description") or "").strip()
            basic_quals = str(item.get("basic_qualifications") or "").strip()
            preferred_quals = str(item.get("preferred_qualifications") or "").strip()
            if basic_quals or preferred_quals:
                parts = [description, basic_quals, preferred_quals]
                description = "\n\n".join(p for p in parts if p)

            postings.append(
                RawJobPosting(
                    source=self.source,
                    company=item.get("company_name") or self.company,
                    payload={
                        "id": str(item.get("id_icims") or item.get("id") or url),
                        "title": title,
                        "location": location,
                        "url": url,
                        "posted_at": str(item.get("posted_date") or item.get("updated_time") or "") or None,
                        "description": description,
                    },
                    url=url,
                )
            )

        return postings

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = str(p.get("location") or "")
        return NormalizedJobPosting(
            source=self.source,
            company=raw.company,
            source_job_id=str(p.get("id") or p.get("url") or ""),
            url=str(p.get("url") or "https://www.amazon.jobs"),
            title=str(p.get("title") or "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(str(p.get("posted_at") or "") or None),
            description_text=str(p.get("description") or ""),
            employment_type=None,
            seniority=None,
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(p)),
        )


__all__ = ["AmazonJobsAdapter"]
