from __future__ import annotations

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class GreenhouseAdapter(SourceAdapter):
    source = "greenhouse_deepmind"
    company = "DeepMind"

    API_URL = "https://boards-api.greenhouse.io/v1/boards/deepmind/jobs?content=true"

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        response = client.get(self.API_URL)
        response.raise_for_status()
        jobs = response.json().get("jobs", [])

        results: list[RawJobPosting] = []
        for job in jobs:
            results.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(job.get("id", "")),
                        "title": job.get("title", ""),
                        "location": (job.get("location") or {}).get("name", ""),
                        "url": job.get("absolute_url", ""),
                        "posted_at": job.get("updated_at"),
                        "description": job.get("content") or "",
                        "employment_type": (job.get("metadata") or {}).get("Employment Type"),
                        "seniority": (job.get("metadata") or {}).get("Seniority"),
                    },
                    url=job.get("absolute_url"),
                )
            )
        return results

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = p.get("location", "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id", p.get("url", ""))),
            url=p.get("url") or "https://job-boards.greenhouse.io/deepmind",
            title=p.get("title", "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(p.get("posted_at")),
            description_text=p.get("description", ""),
            employment_type=p.get("employment_type"),
            seniority=p.get("seniority"),
            raw_snapshot_id="",
            content_hash=self._content_hash(p),
        )
