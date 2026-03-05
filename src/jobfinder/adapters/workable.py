from __future__ import annotations

import logging

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class WorkableAdapter(SourceAdapter):
    source = "workable_huggingface"
    company = "Hugging Face"

    API_URL = "https://apply.workable.com/api/v3/accounts/huggingface/jobs"
    PUBLIC_URL = "https://apply.workable.com/huggingface/?lng=en"
    MAX_PAGES = 10

    DETAIL_URL_TEMPLATE = "https://apply.workable.com/api/v1/accounts/huggingface/jobs/{shortcode}"
    MAX_DETAIL_FETCH = 50

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        jobs = self._fetch_from_api(client)
        if jobs:
            postings = self._from_api_payload(jobs)
            self._enrich_descriptions(postings, client)
            return postings
        return []

    def _fetch_from_api(self, client: httpx.Client) -> list[dict]:
        all_jobs: list[dict] = []
        body: dict = {
            "query": "",
            "location": [],
            "department": [],
            "worktype": [],
            "remote": [],
        }

        for _ in range(self.MAX_PAGES):
            try:
                response = client.post(
                    self.API_URL,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
            except httpx.HTTPError:
                break

            if response.status_code != 200:
                logger.info("Workable API returned %s", response.status_code)
                break

            payload = response.json()
            if not isinstance(payload, dict):
                break

            results = payload.get("results", [])
            if not results:
                break

            all_jobs.extend(results)

            next_page = payload.get("nextPage")
            if not next_page:
                break
            body = {**body, "token": next_page}

        return all_jobs

    def _from_api_payload(self, jobs: list[dict]) -> list[RawJobPosting]:
        out: list[RawJobPosting] = []
        for job in jobs:
            shortcode = str(job.get("shortcode", ""))
            url = f"https://apply.workable.com/huggingface/j/{shortcode}/" if shortcode else ""

            location = self._build_location(job)

            out.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": shortcode,
                        "title": job.get("title", ""),
                        "location": location,
                        "url": url,
                        "posted_at": job.get("published"),
                        "description": job.get("description") or "",
                        "employment_type": job.get("type"),
                        "seniority": job.get("experience"),
                        "remote": job.get("remote", False),
                    },
                    url=url,
                )
            )
        return out

    def _enrich_descriptions(self, postings: list[RawJobPosting], client: httpx.Client) -> None:
        for posting in postings[: self.MAX_DETAIL_FETCH]:
            shortcode = posting.payload.get("id", "")
            if not shortcode:
                continue
            url = self.DETAIL_URL_TEMPLATE.format(shortcode=shortcode)
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            try:
                detail = response.json()
            except Exception:
                continue
            parts = []
            for field in ("description", "requirements", "benefits"):
                text = str(detail.get(field) or "").strip()
                if text:
                    parts.append(text)
            if parts:
                posting.payload["description"] = "\n\n".join(parts)

    def _build_location(self, job: dict) -> str:
        loc = job.get("location")
        if isinstance(loc, dict):
            parts = [
                str(loc.get("city") or ""),
                str(loc.get("region") or ""),
                str(loc.get("country") or ""),
            ]
            location_str = ", ".join(p for p in parts if p)
        else:
            location_str = str(loc or "")

        locations_list = job.get("locations")
        if isinstance(locations_list, list) and len(locations_list) > 1:
            extras = []
            for extra_loc in locations_list[1:]:
                if isinstance(extra_loc, dict):
                    extra_parts = [
                        str(extra_loc.get("city") or ""),
                        str(extra_loc.get("country") or ""),
                    ]
                    extra_str = ", ".join(p for p in extra_parts if p)
                    if extra_str:
                        extras.append(extra_str)
            if extras:
                location_str = "; ".join([location_str, *extras]) if location_str else "; ".join(extras)

        if job.get("remote"):
            location_str = f"{location_str} (Remote)" if location_str else "Remote"

        return location_str

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = p.get("location", "")
        is_remote = p.get("remote", False) or "remote" in str(location_text).lower()
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id", p.get("url", ""))),
            url=p.get("url") or "https://apply.workable.com/huggingface/",
            title=p.get("title", "Unknown role"),
            location_text=location_text,
            is_remote=is_remote,
            posted_at=self._safe_dt(p.get("posted_at")),
            description_text=p.get("description", ""),
            employment_type=p.get("employment_type"),
            seniority=p.get("seniority"),
            raw_snapshot_id="",
            content_hash=self._content_hash(p),
        )
