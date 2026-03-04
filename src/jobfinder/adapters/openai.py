from __future__ import annotations

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class OpenAIAdapter(SourceAdapter):
    source = "openai"
    company = "OpenAI"

    SEARCH_URLS = [
        "https://openai.com/careers/search/",
        "https://openai.com/careers/",
    ]

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        last_error: RuntimeError | None = None
        for url in self.SEARCH_URLS:
            response = client.get(url)
            if response.status_code == 403:
                logger.info("OpenAI careers returned 403 at %s; trying next fallback URL", url)
                last_error = RuntimeError(f"OpenAI careers returned HTTP 403 at {url}")
                continue
            if response.status_code >= 400:
                last_error = RuntimeError(f"OpenAI careers returned HTTP {response.status_code} at {url}")
                continue

            jobs = self._extract_jobs(response.text)
            if jobs:
                for job in jobs:
                    if not str(job.get("description") or "").strip():
                        job["description"] = self._fetch_job_description(client, str(job.get("url") or ""))
                return [
                    RawJobPosting(
                        source=self.source,
                        company=self.company,
                        payload=job,
                        url=job.get("url"),
                    )
                    for job in jobs
                ]

        if last_error is not None:
            raise last_error
        return []

    def _extract_jobs(self, html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")

        jobs: list[dict[str, str | None]] = []
        seen_urls: set[str] = set()

        # Pass 1: Structured data extraction from JSON-LD
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            try:
                blob = json.loads(text)
            except json.JSONDecodeError:
                continue
            entries = blob if isinstance(blob, list) else [blob]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") != "JobPosting":
                    continue
                url = str(entry.get("url") or "")
                title = str(entry.get("title") or "")
                if not url or not title or url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append(
                    {
                        "id": url,
                        "title": title,
                        "location": self._location_from_ld_json(entry),
                        "url": url,
                        "posted_at": entry.get("datePosted"),
                        "description": str(entry.get("description") or ""),
                    }
                )

        # Pass 2: Generic anchor extraction fallback
        for anchor in soup.select("a[href]"):
            title = anchor.get_text(strip=True)
            href = anchor.get("href", "")
            if not title:
                continue
            href_lower = href.lower()
            if "job" not in href_lower and "/careers/" not in href_lower:
                continue
            url = href if href.startswith("http") else f"https://openai.com{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            jobs.append(
                {
                    "id": url,
                    "title": title,
                    "location": "",
                    "url": url,
                    "posted_at": None,
                    "description": "",
                }
            )
        return jobs

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
                "div[class*='job-description']",
                "section[class*='job-description']",
                "article",
                "main",
            ],
        )

    def _location_from_ld_json(self, payload: dict[str, object]) -> str:
        location = payload.get("jobLocation")
        if isinstance(location, dict):
            address = location.get("address")
            if isinstance(address, dict):
                locality = address.get("addressLocality")
                region = address.get("addressRegion")
                country = address.get("addressCountry")
                parts = [str(x) for x in [locality, region, country] if x]
                return ", ".join(parts)
        return ""

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = str(p.get("location") or "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id", p.get("url", ""))),
            url=str(p.get("url") or self.SEARCH_URLS[0]),
            title=str(p.get("title") or "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(str(p.get("posted_at")) if p.get("posted_at") else None),
            description_text=str(p.get("description") or ""),
            employment_type=None,
            seniority=None,
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(p)),
        )
