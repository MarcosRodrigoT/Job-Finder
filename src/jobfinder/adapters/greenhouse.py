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

        # Build location filter terms from profile
        location_terms = [loc.strip().lower() for loc in profile.locations if loc.strip()]
        # Always include "remote" as acceptable
        if "remote" not in location_terms:
            location_terms.append("remote")

        results: list[RawJobPosting] = []
        for job in jobs:
            employment_type = None
            seniority = None
            metadata = job.get("metadata") or []
            if isinstance(metadata, list):
                for item in metadata:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "")
                    value = item.get("value")
                    lowered = name.lower()
                    if "employment" in lowered and value:
                        employment_type = str(value)
                    elif ("senior" in lowered or "level" in lowered) and value:
                        seniority = str(value)

            location_name = (job.get("location") or {}).get("name", "")

            # Filter by profile locations if terms are provided
            if location_terms:
                loc_lower = location_name.lower()
                if not any(term in loc_lower for term in location_terms):
                    continue

            results.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(job.get("id", "")),
                        "title": job.get("title", ""),
                        "location": location_name,
                        "url": job.get("absolute_url", ""),
                        "posted_at": job.get("updated_at"),
                        "description": job.get("content") or "",
                        "employment_type": employment_type,
                        "seniority": seniority,
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
