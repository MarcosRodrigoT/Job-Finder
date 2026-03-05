from __future__ import annotations

import html
import json
import re
from urllib.parse import urljoin, urlparse

import warnings

import httpx
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from bs4.element import Tag

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

from jobfinder.adapters.base import SourceAdapter, SourceBlockedError
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class GenericPublicCareersAdapter(SourceAdapter):
    """API-light adapter that scrapes public careers pages via JSON-LD + anchor heuristics."""

    SEARCH_URLS: tuple[str, ...] = ()
    ALLOWED_DOMAINS: tuple[str, ...] = ()
    JOB_URL_HINTS: tuple[str, ...] = (
        "/job",
        "/jobs",
        "/careers/job",
        "/careers/jobs",
        "/position",
        "/positions",
        "/opening",
        "/openings",
        "/vacanc",
        "/requisition",
        "gh_jid",
        "lever.co",
        "workable.com",
        "greenhouse.io",
    )
    EXCLUDED_URL_HINTS: tuple[str, ...] = (
        "mailto:",
        "javascript:",
        "/privacy",
        "/terms",
        "/cookie",
        "/cookies",
        "/login",
        "/signin",
        "/register",
        "/help",
        "/about",
        "/blog",
        "/press",
    )
    DESCRIPTION_SELECTORS: tuple[str, ...] = (
        "section[data-testid='job-description']",
        "div[data-testid='job-description']",
        "section[class*='job-description']",
        "div[class*='job-description']",
        "article",
        "main",
    )

    MAX_JOBS: int = 300
    MAX_DETAIL_FETCH: int = 90

    KNOWN_EXTERNAL_JOB_DOMAINS: tuple[str, ...] = (
        "greenhouse.io",
        "lever.co",
        "workable.com",
        "ashbyhq.com",
        "smartrecruiters.com",
        "myworkdayjobs.com",
        "jobvite.com",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        return list(dict.fromkeys(self.SEARCH_URLS))

    def default_url(self) -> str:
        if self.SEARCH_URLS:
            return self.SEARCH_URLS[0]
        return "https://example.com"

    def _keyword_query(self, profile: SearchProfile) -> str:
        terms = [term.strip() for term in profile.role_terms() if term.strip()]
        if terms:
            return " ".join(terms[:5])
        return "machine learning"

    def _location_query(self, profile: SearchProfile) -> str:
        for location in profile.locations:
            cleaned = location.strip()
            if cleaned and cleaned.lower() != "remote":
                return cleaned
        return "Spain"

    WAIT_SELECTOR: str | None = None

    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: object | None = None,
    ) -> list[RawJobPosting]:
        search_urls = self.build_search_urls(profile)
        if not search_urls:
            return []

        blocked_count = 0
        extracted: list[dict[str, str | None]] = []

        for url in search_urls:
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue

            if response.status_code in {403, 429}:
                blocked_count += 1
                continue
            if response.status_code >= 400:
                continue

            extracted.extend(self._extract_jobs(response.text, base_url=url, profile=profile))

        if extracted:
            static_postings = self._to_raw_postings(extracted, client)
            # If we got a decent number of results, return them
            if len(static_postings) >= 3 or browser_ctx is None:
                return static_postings
            # Try browser for better results
            browser_jobs = self._fetch_with_browser(search_urls, profile, client)
            if browser_jobs and len(browser_jobs) > len(static_postings):
                return browser_jobs
            return static_postings

        # Fall back to browser rendering if available and static fetch failed
        if browser_ctx is not None:
            browser_jobs = self._fetch_with_browser(search_urls, profile, client)
            if browser_jobs:
                return browser_jobs

        if blocked_count == len(search_urls):
            raise SourceBlockedError(f"{self.source} blocked all search requests")

        return []

    def _fetch_with_browser(
        self,
        search_urls: list[str],
        profile: SearchProfile,
        client: httpx.Client,
    ) -> list[RawJobPosting]:
        from jobfinder.adapters.browser import fetch_rendered_html

        extracted: list[dict[str, str | None]] = []
        for url in search_urls:
            rendered_html = fetch_rendered_html(
                url, wait_selector=self.WAIT_SELECTOR,
            )
            if rendered_html:
                extracted.extend(self._extract_jobs(rendered_html, base_url=url, profile=profile))

        if extracted:
            return self._to_raw_postings(extracted, client)
        return []

    def _to_raw_postings(self, jobs: list[dict[str, str | None]], client: httpx.Client) -> list[RawJobPosting]:
        deduped: dict[str, dict[str, str | None]] = {}

        for candidate in jobs:
            url = str(candidate.get("url") or "").strip()
            title = str(candidate.get("title") or "").strip()
            if not url or not title:
                continue
            if not self._is_candidate_job_url(url):
                continue

            if url not in deduped:
                description = self._normalize_description_value(candidate.get("description"))
                deduped[url] = {
                    "id": str(candidate.get("id") or url),
                    "title": title,
                    "location": str(candidate.get("location") or ""),
                    "url": url,
                    "posted_at": str(candidate.get("posted_at") or "") or None,
                    "description": description,
                }

        ordered_jobs = list(deduped.values())[: self.MAX_JOBS]

        enriched: list[RawJobPosting] = []
        for index, payload in enumerate(ordered_jobs):
            description = str(payload.get("description") or "")
            if index < self.MAX_DETAIL_FETCH:
                detail = self._fetch_job_description(client, str(payload.get("url") or ""))
                if self._is_better_description(detail, description):
                    description = detail
            payload["description"] = description

            enriched.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload=payload,
                    url=str(payload.get("url") or ""),
                )
            )

        return enriched

    def _extract_jobs(self, html: str, base_url: str, profile: SearchProfile) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")

        jobs: list[dict[str, str | None]] = []
        jobs.extend(self._extract_jobs_from_json_ld(soup, base_url=base_url))
        jobs.extend(self._extract_jobs_from_anchors(soup, base_url=base_url, profile=profile))
        jobs.extend(self._extract_jobs_from_script_urls(soup, base_url=base_url))

        return jobs

    def _extract_jobs_from_json_ld(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            for entry in self._iter_json_entries(text):
                if not isinstance(entry, dict):
                    continue
                if not self._is_job_posting_entry(entry):
                    continue
                url = str(entry.get("url") or "").strip()
                title = str(entry.get("title") or "").strip()
                if not url or not title:
                    continue
                full_url = urljoin(base_url, url)
                jobs.append(
                    {
                        "id": str(entry.get("identifier") or full_url),
                        "title": title,
                        "location": self._location_from_job_posting(entry),
                        "url": full_url,
                        "posted_at": str(entry.get("datePosted") or "") or None,
                        "description": self._normalize_description_value(entry.get("description")),
                    }
                )
        return jobs

    def _extract_jobs_from_anchors(
        self,
        soup: BeautifulSoup,
        base_url: str,
        profile: SearchProfile,
    ) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []

        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            url = urljoin(base_url, href)
            if not self._is_candidate_job_url(url):
                continue

            title = self._title_from_anchor(anchor)
            if not self._looks_like_job_title(title):
                continue

            location = self._infer_location(anchor, profile)
            jobs.append(
                {
                    "id": url,
                    "title": title,
                    "location": location,
                    "url": url,
                    "posted_at": None,
                    "description": None,
                }
            )

        return jobs

    def _extract_jobs_from_script_urls(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []
        pattern = re.compile(r"https?://[^\s'\"<>\\]+")

        for script in soup.select("script"):
            text = script.string or script.get_text() or ""
            if "job" not in text.lower() and "career" not in text.lower():
                continue
            for match in pattern.findall(text):
                url = urljoin(base_url, match)
                if not self._is_candidate_job_url(url):
                    continue
                jobs.append(
                    {
                        "id": url,
                        "title": self._title_from_url(url),
                        "location": "",
                        "url": url,
                        "posted_at": None,
                        "description": None,
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

        return self._extract_best_description(response.text)

    def _extract_best_description(self, html_text: str) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup.select("script,style,noscript,svg,iframe"):
            tag.decompose()

        selectors = [
            *self.DESCRIPTION_SELECTORS,
            "[data-autom='job-description']",
            "section[id*='job-description']",
            "div[id*='job-description']",
            "section[id*='description']",
            "div[id*='description']",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node is None:
                continue
            for tag in node.select("script,style,noscript,svg,iframe,header,footer,nav,aside"):
                tag.decompose()
            rich_html = node.decode_contents().strip()
            normalized = self._normalize_description_value(rich_html)
            if self._description_quality(normalized) >= 4:
                return normalized

        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            for entry in self._iter_json_entries(text):
                if not isinstance(entry, dict):
                    continue
                if not self._is_job_posting_entry(entry):
                    continue
                normalized = self._normalize_description_value(entry.get("description"))
                if normalized:
                    return normalized

        return ""

    def _normalize_description_value(self, value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        for _ in range(3):
            unescaped = html.unescape(text)
            if unescaped == text:
                break
            text = unescaped
        return text.strip()

    def _description_quality(self, description: str) -> int:
        if not description:
            return 0
        plain = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        words = [word for word in plain.split() if word.strip()]
        return len(words)

    def _is_better_description(self, candidate: str, current: str) -> bool:
        return self._description_quality(candidate) > self._description_quality(current)

    def _is_job_posting_entry(self, entry: dict[str, object]) -> bool:
        entry_type = entry.get("@type")
        if isinstance(entry_type, str):
            return entry_type.lower() == "jobposting"
        if isinstance(entry_type, list):
            return any(str(v).lower() == "jobposting" for v in entry_type)
        return False

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

    def _location_from_job_posting(self, payload: dict[str, object]) -> str:
        location = payload.get("jobLocation")
        if isinstance(location, dict):
            return self._location_from_location_obj(location)
        if isinstance(location, list):
            parts: list[str] = []
            for item in location:
                if isinstance(item, dict):
                    loc = self._location_from_location_obj(item)
                    if loc:
                        parts.append(loc)
            return ", ".join(dict.fromkeys(parts))
        return ""

    def _location_from_location_obj(self, location_obj: dict[str, object]) -> str:
        address = location_obj.get("address")
        if not isinstance(address, dict):
            return ""
        parts = [
            str(address.get("addressLocality") or "").strip(),
            str(address.get("addressRegion") or "").strip(),
            str(address.get("addressCountry") or "").strip(),
        ]
        return ", ".join([part for part in parts if part])

    def _title_from_anchor(self, anchor: Tag) -> str:
        title = anchor.get_text(" ", strip=True)
        if title:
            return title
        for attr in ("aria-label", "title"):
            value = str(anchor.get(attr) or "").strip()
            if value:
                return value
        return ""

    def _title_from_url(self, url: str) -> str:
        slug = urlparse(url).path.rsplit("/", 1)[-1]
        slug = slug.replace("-", " ").replace("_", " ").strip()
        # Reject pure numeric slugs (job IDs, not titles)
        if not slug or slug.replace(" ", "").isdigit():
            return ""
        return slug.title()

    def _infer_location(self, anchor: Tag, profile: SearchProfile) -> str:
        parent = anchor.find_parent(["article", "li", "div", "section", "tr"])
        context = parent.get_text(" ", strip=True) if parent is not None else ""
        lowered = context.lower()

        candidates = [*profile.locations, "Madrid", "Spain", "Barcelona", "Remote", "EMEA", "Europe"]
        found: list[str] = []
        for candidate in candidates:
            cleaned = candidate.strip()
            if cleaned and cleaned.lower() in lowered:
                found.append(cleaned)

        if found:
            return ", ".join(dict.fromkeys(found))
        return ""

    def _looks_like_job_title(self, title: str) -> bool:
        cleaned = title.strip()
        if len(cleaned) < 3 or len(cleaned) > 160:
            return False

        lowered = cleaned.lower()
        banned = {
            "apply",
            "apply now",
            "learn more",
            "read more",
            "view all",
            "privacy",
            "cookie policy",
            "terms",
            "home",
            "careers",
            "jobs",
        }
        if lowered in banned:
            return False

        non_alpha_ratio = sum(1 for char in cleaned if not char.isalnum() and not char.isspace()) / max(1, len(cleaned))
        return non_alpha_ratio < 0.30

    def _is_candidate_job_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        lower_url = url.lower()
        if any(hint in lower_url for hint in self.EXCLUDED_URL_HINTS):
            return False

        domain = (parsed.netloc or "").lower()
        if self.ALLOWED_DOMAINS and not any(domain.endswith(allowed) for allowed in self.ALLOWED_DOMAINS):
            if not any(domain.endswith(known) for known in self.KNOWN_EXTERNAL_JOB_DOMAINS):
                return False

        if any(hint in lower_url for hint in self.JOB_URL_HINTS):
            return True

        return any(domain.endswith(known) for known in self.KNOWN_EXTERNAL_JOB_DOMAINS)

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        payload = raw.payload
        location_text = str(payload.get("location") or "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(payload.get("id") or payload.get("url") or ""),
            url=str(payload.get("url") or self.default_url()),
            title=str(payload.get("title") or "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(str(payload.get("posted_at") or "") or None),
            description_text=str(payload.get("description") or ""),
            employment_type=str(payload.get("employment_type") or "") or None,
            seniority=str(payload.get("seniority") or "") or None,
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(payload)),
        )


__all__ = ["GenericPublicCareersAdapter"]
