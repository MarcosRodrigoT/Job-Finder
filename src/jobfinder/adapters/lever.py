from __future__ import annotations

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class LeverAdapter(SourceAdapter):
    source = "lever_mistral"
    company = "Mistral AI"

    API_URL = "https://api.lever.co/v0/postings/mistral?mode=json"

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        response = client.get(self.API_URL)
        response.raise_for_status()
        jobs = response.json()

        out: list[RawJobPosting] = []
        for job in jobs:
            description = job.get("description") or job.get("descriptionPlain") or ""
            out.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(job.get("id", "")),
                        "title": job.get("text", ""),
                        "location": (job.get("categories") or {}).get("location", ""),
                        "url": job.get("hostedUrl", ""),
                        "posted_at": job.get("createdAt"),
                        "description": description,
                        "employment_type": (job.get("categories") or {}).get("commitment"),
                        "seniority": (job.get("categories") or {}).get("team"),
                    },
                    url=job.get("hostedUrl"),
                )
            )
        return out

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = p.get("location", "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id", p.get("url", ""))),
            url=p.get("url") or "https://jobs.lever.co/mistral",
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
