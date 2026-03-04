from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class AppleJobsAdapter(GenericPublicCareersAdapter):
    source = "apple"
    company = "Apple"

    ROOT_URL = "https://jobs.apple.com/en-us/search"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("jobs.apple.com", "apple.com")
    JOB_URL_HINTS = GenericPublicCareersAdapter.JOB_URL_HINTS + ("/details/",)
    DESCRIPTION_SELECTORS = (
        "[data-autom='job-description']",
        "[data-testid='job-description']",
        "section[id*='job-description']",
        "div[id*='job-description']",
        "section[class*='job-description']",
        "div[class*='job-description']",
        "div#job-description",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        params = {
            "search": self._keyword_query(profile),
            "sort": "relevance",
            "location": "spain-ESPC",
        }
        return [f"{self.ROOT_URL}?{urlencode(params)}"]

    def _is_candidate_job_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if not parsed.netloc.lower().endswith("jobs.apple.com"):
            return False

        path = parsed.path.lower()
        if "/details/" not in path:
            return False
        if "locationpicker" in path:
            return False
        if "choose-country-region" in path:
            return False
        return True

    def _fetch_job_description(self, client: httpx.Client, url: str) -> str:
        if not url:
            return ""
        try:
            response = client.get(url)
        except httpx.HTTPError:
            return ""
        if response.status_code >= 400:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        best = ""

        for selector in self.DESCRIPTION_SELECTORS:
            node = soup.select_one(selector)
            if node is None:
                continue
            for tag in node.select("script,style,noscript,svg,iframe,header,footer,nav,aside"):
                tag.decompose()
            rich_html = node.decode_contents().strip()
            normalized = self._normalize_description_value(rich_html)
            if self._description_quality(normalized) > self._description_quality(best):
                best = normalized
        if self._description_quality(best) >= 12:
            return best

        script_best = self._extract_description_from_scripts(soup)
        if self._description_quality(script_best) > self._description_quality(best):
            best = script_best

        if self._description_quality(best) >= 12:
            return best

        # As a final fallback, reuse the generic extraction path.
        generic = super()._fetch_job_description(client, url)
        if self._description_quality(generic) > self._description_quality(best):
            best = generic

        if self._looks_like_apple_chrome(best):
            return ""

        return best

    def _extract_description_from_scripts(self, soup: BeautifulSoup) -> str:
        best = ""
        for script in soup.select("script[type='application/ld+json']"):
            blob = script.string or script.get_text() or ""
            if not blob.strip():
                continue
            try:
                loaded = json.loads(blob)
            except json.JSONDecodeError:
                continue
            entries = loaded if isinstance(loaded, list) else [loaded]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not self._is_job_posting_entry(entry):
                    continue
                description = self._normalize_description_value(entry.get("description"))
                if self._description_quality(description) > self._description_quality(best):
                    best = description

        for script in soup.select("script#__NEXT_DATA__, script[type='application/json']"):
            blob = script.string or script.get_text() or ""
            if not blob.strip():
                continue
            try:
                loaded = json.loads(blob)
            except json.JSONDecodeError:
                continue
            candidate = self._extract_description_from_json_blob(loaded)
            if self._description_quality(candidate) > self._description_quality(best):
                best = candidate

        # Apple uses React Router with window.__staticRouterHydrationData = JSON.parse("...")
        for script in soup.select("script"):
            text = script.string or script.get_text() or ""
            if "__staticRouterHydrationData" not in text:
                continue
            match = re.search(r'JSON\.parse\("((?:[^"\\]|\\.)*)"\)', text, re.DOTALL)
            if not match:
                continue
            raw = match.group(1)
            try:
                json_string = json.loads('"' + raw + '"')
                loaded = json.loads(json_string)
            except (json.JSONDecodeError, ValueError):
                continue
            candidate = self._extract_description_from_apple_hydration(loaded)
            if not candidate:
                candidate = self._extract_description_from_json_blob(loaded)
            if self._description_quality(candidate) > self._description_quality(best):
                best = candidate

        return best

    def _extract_description_from_apple_hydration(self, data: object) -> str:
        if not isinstance(data, dict):
            return ""
        try:
            posting = (
                data
                .get("loaderData", {})
                .get("jobDetails", {})
                .get("jobsData", {})
                .get("localizations", {})
                .get("en_US", {})
                .get("posting", {})
            )
        except AttributeError:
            return ""
        if not isinstance(posting, dict):
            return ""
        parts = []
        for key in ("jobSummary", "description", "minimumQualifications", "preferredQualifications"):
            value = posting.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n\n".join(parts)

    def _extract_description_from_json_blob(self, payload: object) -> str:
        best = ""
        preferred_tokens = (
            "description",
            "jobdescription",
            "summary",
            "responsibil",
            "qualification",
            "about",
        )

        def walk(node: object, key_hint: str = "") -> None:
            nonlocal best
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, key_hint=str(key).lower())
                return
            if isinstance(node, list):
                for item in node:
                    walk(item, key_hint=key_hint)
                return
            if not isinstance(node, str):
                return

            text = self._normalize_description_value(node)
            if not text:
                return

            quality = self._description_quality(text)
            if quality < 5:
                return
            if preferred_tokens and not any(token in key_hint for token in preferred_tokens):
                if quality < 40:
                    return
            if self._looks_like_apple_chrome(text):
                return

            if quality > self._description_quality(best):
                best = text

        walk(payload)
        return best

    def _looks_like_apple_chrome(self, text: str) -> bool:
        lowered = text.lower()
        markers = (
            "apple footer",
            "shop and learn",
            "privacy policy",
            "terms of use",
            "site map",
            "apple store",
            "copyright",
        )
        hits = sum(1 for marker in markers if marker in lowered)
        return hits >= 3


__all__ = ["AppleJobsAdapter"]
