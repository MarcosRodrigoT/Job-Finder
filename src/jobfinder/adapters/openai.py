from __future__ import annotations

import json
import logging
from urllib.parse import urljoin

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

    ASHBY_API_URL = "https://api.ashbyhq.com/posting-api/job-board/openai"

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        openai_jobs, openai_error = self._fetch_from_openai_pages(client)
        if openai_jobs:
            return self._to_raw_postings(openai_jobs, client)

        ashby_jobs = self._fetch_from_ashby_api(client)
        if ashby_jobs:
            logger.info("OpenAI adapter is using Ashby API fallback (%s jobs)", len(ashby_jobs))
            return self._to_raw_postings(ashby_jobs, client)

        if openai_error is not None:
            raise openai_error
        return []

    def _fetch_from_openai_pages(self, client: httpx.Client) -> tuple[list[dict[str, str | None]], RuntimeError | None]:
        last_error: RuntimeError | None = None
        for url in self.SEARCH_URLS:
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code == 403:
                logger.info("OpenAI careers returned 403 at %s; trying next fallback URL", url)
                last_error = RuntimeError(f"OpenAI careers returned HTTP 403 at {url}")
                continue
            if response.status_code >= 400:
                last_error = RuntimeError(f"OpenAI careers returned HTTP {response.status_code} at {url}")
                continue

            jobs = self._extract_jobs_from_html(response.text, base_url="https://openai.com")
            if jobs:
                return jobs, None

        return [], last_error

    def _fetch_from_ashby_api(self, client: httpx.Client) -> list[dict[str, str | None]]:
        try:
            response = client.get(self.ASHBY_API_URL)
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, dict):
            return []

        raw_jobs = payload.get("jobs")
        if not isinstance(raw_jobs, list):
            return []

        jobs: list[dict[str, str | None]] = []
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
            title = str(job.get("title") or "").strip()
            if not title:
                continue

            job_id = str(job.get("id") or "")
            url = f"https://jobs.ashbyhq.com/openai/{job_id}" if job_id else None

            location = str(job.get("location") or "")
            secondary = job.get("secondaryLocations")
            if isinstance(secondary, list) and secondary:
                extras: list[str] = []
                for loc in secondary:
                    if isinstance(loc, dict):
                        loc_name = str(loc.get("location") or "").strip()
                        if loc_name:
                            extras.append(loc_name)
                    elif loc:
                        extras.append(str(loc))
                if extras:
                    location = ", ".join([location, *extras]) if location else ", ".join(extras)

            employment_type = str(job.get("employmentType") or "") or None
            department = str(job.get("department") or "") or None
            description = str(job.get("descriptionPlain") or job.get("descriptionHtml") or "").strip() or None

            jobs.append({
                "id": job_id or title,
                "title": title,
                "location": location,
                "url": url,
                "posted_at": str(job.get("publishedAt") or "") or None,
                "description": description,
                "employment_type": employment_type,
                "seniority": department,
            })

        return jobs

    def _to_raw_postings(self, jobs: list[dict[str, str | None]], client: httpx.Client) -> list[RawJobPosting]:
        unique: dict[str, dict[str, str | None]] = {}
        for job in jobs:
            url = str(job.get("url") or "").strip()
            title = str(job.get("title") or "").strip()
            if not url or not title:
                continue
            if url in unique:
                continue
            unique[url] = {
                "id": str(job.get("id") or url),
                "title": title,
                "location": str(job.get("location") or ""),
                "url": url,
                "posted_at": str(job.get("posted_at") or "") or None,
                "description": str(job.get("description") or ""),
                "employment_type": job.get("employment_type"),
                "seniority": job.get("seniority"),
            }

        postings: list[RawJobPosting] = []
        for payload in unique.values():
            postings.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload=payload,
                    url=str(payload.get("url") or ""),
                )
            )
        return postings

    def _extract_jobs_from_html(self, html: str, base_url: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")

        jobs: list[dict[str, str | None]] = []
        seen_urls: set[str] = set()

        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            for entry in self._iter_json_entries(text):
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("@type") or "").lower() != "jobposting":
                    continue
                url = str(entry.get("url") or "")
                title = str(entry.get("title") or "")
                if not url or not title:
                    continue
                absolute_url = url if url.startswith("http") else urljoin(base_url, url)
                if absolute_url in seen_urls:
                    continue
                seen_urls.add(absolute_url)
                jobs.append(
                    {
                        "id": absolute_url,
                        "title": title,
                        "location": self._location_from_ld_json(entry),
                        "url": absolute_url,
                        "posted_at": str(entry.get("datePosted") or "") or None,
                        "description": str(entry.get("description") or "") or None,
                    }
                )

        for anchor in soup.select("a[href]"):
            title = anchor.get_text(strip=True)
            href = str(anchor.get("href") or "")
            if not title:
                continue
            href_lower = href.lower()
            if "job" not in href_lower and "/careers/" not in href_lower and "opening" not in href_lower:
                continue
            url = href if href.startswith("http") else urljoin(base_url, href)
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
                    "description": None,
                }
            )

        return jobs

    def _iter_json_entries(self, raw_json: str) -> list[object]:
        try:
            blob = json.loads(raw_json)
        except json.JSONDecodeError:
            return []

        entries: list[object] = []

        def walk(node: object) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if isinstance(node, dict):
                entries.append(node)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    for item in graph:
                        walk(item)

        walk(blob)
        return entries

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
            employment_type=(str(p.get("employment_type")) if p.get("employment_type") else None),
            seniority=(str(p.get("seniority")) if p.get("seniority") else None),
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(p)),
        )
