from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class WorkableAdapter(SourceAdapter):
    source = "workable_huggingface"
    company = "Hugging Face"

    API_URL = "https://apply.workable.com/api/v3/accounts/huggingface/jobs"
    PUBLIC_URL = "https://apply.workable.com/huggingface/?lng=en"

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        response = client.get(self.API_URL)
        jobs: list[dict] = []
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                jobs = list(payload.get("results", []))
        else:
            logger.info("Workable API returned %s, falling back to public HTML parse", response.status_code)

        if jobs:
            return self._from_api_payload(jobs)
        return self._from_public_html(client)

    def _from_api_payload(self, jobs: list[dict]) -> list[RawJobPosting]:
        out: list[RawJobPosting] = []
        for job in jobs:
            out.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(job.get("shortcode", "")),
                        "title": job.get("title", ""),
                        "location": (job.get("location") or {}).get("location_str", ""),
                        "url": job.get("url", ""),
                        "posted_at": job.get("published"),
                        "description": job.get("description") or "",
                        "employment_type": job.get("type"),
                        "seniority": job.get("experience"),
                    },
                    url=job.get("url"),
                )
            )
        return out

    def _from_public_html(self, client: httpx.Client) -> list[RawJobPosting]:
        response = client.get(self.PUBLIC_URL)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        out: list[RawJobPosting] = []
        seen_urls: set[str] = set()

        for anchor in soup.select("a[href*='/j/'], a[href*='/jobs/'], a[href*='job']"):
            href = (anchor.get("href") or "").strip()
            title = anchor.get_text(strip=True)
            if not href or not title:
                continue
            if not href.startswith("http"):
                href = f"https://apply.workable.com{href}"
            if href in seen_urls:
                continue
            seen_urls.add(href)

            container_text = ""
            parent = anchor.find_parent(["article", "li", "div"])
            if parent is not None:
                container_text = parent.get_text(" ", strip=True)
            location_match = re.search(r"(Madrid|Spain|Remote|Barcelona)", container_text, re.IGNORECASE)
            location = location_match.group(1) if location_match else ""
            description = self._fetch_job_description(client, href)

            out.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": href.rsplit("/", 1)[-1],
                        "title": title,
                        "location": location,
                        "url": href,
                        "posted_at": None,
                        "description": description,
                        "employment_type": None,
                        "seniority": None,
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
                "section[data-ui='job-description']",
                "div[data-ui='job-description']",
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
            url=p.get("url") or "https://apply.workable.com/huggingface/",
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
