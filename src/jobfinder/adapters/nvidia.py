from __future__ import annotations

import logging

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class NvidiaCareersAdapter(SourceAdapter):
    source = "nvidia"
    company = "NVIDIA"

    WORKDAY_API_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    BASE_JOB_URL = "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    PAGE_SIZE = 20
    MAX_PAGES = 10

    DETAIL_API_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
    MAX_DETAIL_FETCH = 50

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        search_text = self._keyword_query(profile)
        all_jobs = self._fetch_from_workday_api(client, search_text)
        if not all_jobs:
            # Try simpler query as fallback
            all_jobs = self._fetch_from_workday_api(client, "machine learning")
        logger.info("NVIDIA fetched %d raw jobs", len(all_jobs))
        postings = self._to_raw_postings(all_jobs)
        self._enrich_descriptions(postings, client)
        return postings

    def _keyword_query(self, profile: SearchProfile) -> str:
        terms = [term.strip() for term in profile.role_terms() if term.strip()]
        if terms:
            return " ".join(terms[:5])
        return "machine learning"

    def _fetch_from_workday_api(self, client: httpx.Client, search_text: str) -> list[dict]:
        all_jobs: list[dict] = []

        for page in range(self.MAX_PAGES):
            offset = page * self.PAGE_SIZE
            body = {
                "appliedFacets": {},
                "limit": self.PAGE_SIZE,
                "offset": offset,
                "searchText": search_text,
            }
            try:
                response = client.post(
                    self.WORKDAY_API_URL,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
            except httpx.HTTPError:
                break

            if response.status_code != 200:
                logger.info("NVIDIA Workday API returned %s", response.status_code)
                break

            payload = response.json()
            if not isinstance(payload, dict):
                break

            job_postings = payload.get("jobPostings", [])
            if not job_postings:
                break

            all_jobs.extend(job_postings)

            total = payload.get("total", 0)
            if offset + self.PAGE_SIZE >= total:
                break

        return all_jobs

    def _to_raw_postings(self, jobs: list[dict]) -> list[RawJobPosting]:
        postings: list[RawJobPosting] = []
        seen_urls: set[str] = set()

        for job in jobs:
            title = str(job.get("title") or "").strip()
            if not title:
                continue

            external_path = str(job.get("externalPath") or "").strip()
            if not external_path:
                continue

            url = f"{self.BASE_JOB_URL}{external_path}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            location = str(job.get("locationsText") or "")
            posted_on = str(job.get("postedOn") or "") or None
            bullet_fields = job.get("bulletFields", [])
            job_id = bullet_fields[0] if bullet_fields else external_path

            postings.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(job_id),
                        "title": title,
                        "location": location,
                        "url": url,
                        "posted_at": posted_on,
                        "description": "",
                        "_external_path": external_path,
                    },
                    url=url,
                )
            )

        return postings

    def _enrich_descriptions(self, postings: list[RawJobPosting], client: httpx.Client) -> None:
        for posting in postings[:self.MAX_DETAIL_FETCH]:
            external_path = posting.payload.get("_external_path", "")
            if not external_path:
                continue
            url = f"{self.DETAIL_API_URL}{external_path}"
            try:
                response = client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            try:
                detail = response.json()
            except Exception:
                continue
            if not isinstance(detail, dict):
                continue
            job_data = detail.get("jobPostingInfo", {})
            description = str(job_data.get("jobDescription") or "").strip()
            if description:
                posting.payload["description"] = description

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = str(p.get("location") or "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id") or p.get("url") or ""),
            url=str(p.get("url") or self.BASE_JOB_URL),
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


__all__ = ["NvidiaCareersAdapter"]
