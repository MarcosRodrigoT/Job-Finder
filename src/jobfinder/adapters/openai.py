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

    # Fallbacks used when openai.com returns bot-protection responses.
    GREENHOUSE_API_URLS = [
        "https://boards-api.greenhouse.io/v1/boards/openai/jobs?content=true",
    ]
    ASHBY_URLS = [
        "https://jobs.ashbyhq.com/openai",
        "https://jobs.ashbyhq.com/OpenAI",
    ]

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        openai_jobs, openai_error = self._fetch_from_openai_pages(client)
        if openai_jobs:
            return self._to_raw_postings(openai_jobs, client)

        greenhouse_jobs = self._fetch_from_greenhouse_api(client)
        if greenhouse_jobs:
            logger.info("OpenAI adapter is using Greenhouse fallback (%s jobs)", len(greenhouse_jobs))
            return self._to_raw_postings(greenhouse_jobs, client)

        ashby_jobs = self._fetch_from_ashby_pages(client)
        if ashby_jobs:
            logger.info("OpenAI adapter is using Ashby fallback (%s jobs)", len(ashby_jobs))
            return self._to_raw_postings(ashby_jobs, client)

        if openai_error is not None:
            raise openai_error
        return []

    def _fetch_from_openai_pages(self, client: httpx.Client) -> tuple[list[dict[str, str | None]], RuntimeError | None]:
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

            jobs = self._extract_jobs_from_html(response.text, base_url="https://openai.com")
            if jobs:
                return jobs, None

        return [], last_error

    def _fetch_from_greenhouse_api(self, client: httpx.Client) -> list[dict[str, str | None]]:
        for url in self.GREENHOUSE_API_URLS:
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            try:
                payload = response.json()
            except json.JSONDecodeError:
                continue

            jobs = self._extract_jobs_from_greenhouse_payload(payload)
            if jobs:
                return jobs
        return []

    def _fetch_from_ashby_pages(self, client: httpx.Client) -> list[dict[str, str | None]]:
        for url in self.ASHBY_URLS:
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code >= 400:
                continue

            jobs = self._extract_jobs_from_ashby_html(response.text, base_url=url)
            if jobs:
                return jobs
        return []

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
            }

        postings: list[RawJobPosting] = []
        for payload in unique.values():
            if not str(payload.get("description") or "").strip():
                payload["description"] = self._fetch_job_description(client, str(payload.get("url") or ""))
            postings.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload=payload,
                    url=str(payload.get("url") or ""),
                )
            )
        return postings

    def _extract_jobs_from_greenhouse_payload(self, payload: object) -> list[dict[str, str | None]]:
        if not isinstance(payload, dict):
            return []

        rows = payload.get("jobs")
        if not isinstance(rows, list):
            return []

        jobs: list[dict[str, str | None]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("absolute_url") or "").strip()
            if not title or not url:
                continue

            location_obj = row.get("location")
            location = ""
            if isinstance(location_obj, dict):
                location = str(location_obj.get("name") or "")

            metadata = row.get("metadata")
            employment_type: str | None = None
            seniority: str | None = None
            if isinstance(metadata, list):
                for item in metadata:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "")
                    value = str(item.get("value") or "")
                    lowered = name.lower()
                    if "employment" in lowered and value:
                        employment_type = value
                    if ("senior" in lowered or "level" in lowered) and value:
                        seniority = value

            jobs.append(
                {
                    "id": str(row.get("id") or url),
                    "title": title,
                    "location": location,
                    "url": url,
                    "posted_at": str(row.get("updated_at") or row.get("first_published") or "") or None,
                    "description": str(row.get("content") or "") or None,
                    "employment_type": employment_type,
                    "seniority": seniority,
                }
            )

        return jobs

    def _extract_jobs_from_ashby_html(self, html: str, base_url: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, str | None]] = []
        seen_urls: set[str] = set()

        # Attempt 1: Next.js data blob used by many Ashby boards.
        next_data = soup.select_one("script#__NEXT_DATA__")
        if next_data is not None:
            text = next_data.string or next_data.get_text() or ""
            if text.strip():
                try:
                    blob = json.loads(text)
                    jobs.extend(self._extract_jobs_from_ashby_json(blob, base_url=base_url))
                except json.JSONDecodeError:
                    pass

        # Attempt 2: parse generic anchors.
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            title = anchor.get_text(" ", strip=True)
            if not href or not title:
                continue
            href_lower = href.lower()
            if "job" not in href_lower and "opening" not in href_lower and "/positions/" not in href_lower:
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

    def _extract_jobs_from_ashby_json(self, payload: object, base_url: str) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []

        def walk(node: object) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if not isinstance(node, dict):
                return

            title = str(node.get("title") or node.get("jobTitle") or "").strip()
            href = str(
                node.get("jobUrl")
                or node.get("absoluteUrl")
                or node.get("url")
                or node.get("externalUrl")
                or ""
            ).strip()
            if title and href:
                url = href if href.startswith("http") else urljoin(base_url, href)
                jobs.append(
                    {
                        "id": str(node.get("id") or url),
                        "title": title,
                        "location": str(node.get("location") or node.get("locationName") or ""),
                        "url": url,
                        "posted_at": str(node.get("publishedAt") or node.get("createdAt") or "") or None,
                        "description": str(node.get("descriptionHtml") or node.get("description") or "") or None,
                    }
                )

            for value in node.values():
                walk(value)

        walk(payload)
        return jobs

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
                "[data-autom='job-description']",
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
            employment_type=(str(p.get("employment_type")) if p.get("employment_type") else None),
            seniority=(str(p.get("seniority")) if p.get("seniority") else None),
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(p)),
        )
