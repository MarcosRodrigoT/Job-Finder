from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class GoogleCareersAdapter(GenericPublicCareersAdapter):
    source = "google"
    company = "Google"

    ROOT_URL = "https://www.google.com/about/careers/applications/jobs/results/"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("google.com", "www.google.com", "careers.google.com")
    EXCLUDED_URL_HINTS = (
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
        "/blog",
        "/press",
    )
    WAIT_SELECTOR = "li.lLd3Je"
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def _extract_jobs(self, html: str, base_url: str, profile: SearchProfile) -> list[dict[str, str | None]]:
        """Override to handle Google's SPA-style relative links."""
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, str | None]] = []

        # Google uses li.lLd3Je for job cards with relative links like
        # "jobs/results/12345-title?q=..." which need special handling
        for item in soup.select("li.lLd3Je"):
            anchor = item.select_one("a[href]")
            if not anchor:
                continue
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue

            # Extract the job ID from relative paths like "jobs/results/12345-title"
            match = re.search(r"(\d+-[a-z0-9-]+)", href)
            if not match:
                continue
            slug = match.group(1)
            url = f"{self.ROOT_URL}{slug}"

            # Text is in the li, not the anchor (which may be empty)
            raw_text = item.get_text(" ", strip=True)
            # Clean up icon text ligatures
            for noise in ("corporate_fare", "place", "bar_chart"):
                raw_text = raw_text.replace(noise, "|")
            parts = [p.strip() for p in raw_text.split("|") if p.strip()]
            title = parts[0] if parts else ""

            if not title or len(title) < 3:
                continue

            location = self._infer_location(item, profile)
            jobs.append({
                "id": url,
                "title": title,
                "location": location,
                "url": url,
                "posted_at": None,
                "description": None,
            })

        # Also try the standard extraction for JSON-LD etc.
        jobs.extend(super()._extract_jobs(html, base_url=base_url, profile=profile))
        return jobs

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        query = self._keyword_query(profile)
        location = self._location_query(profile)

        strict = f"\"{profile.target_roles[0] if profile.target_roles else 'AI'}\" OR \"machine learning\""

        return [
            f"{self.ROOT_URL}?{urlencode({'q': query, 'location': location})}",
            f"{self.ROOT_URL}?{urlencode({'q': strict, 'location': location})}",
        ]


__all__ = ["GoogleCareersAdapter"]
