from __future__ import annotations

from urllib.parse import urlencode

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class IBMCareersAdapter(GenericPublicCareersAdapter):
    source = "ibm"
    company = "IBM"

    ROOT_URL = "https://www.ibm.com/careers/search"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("ibm.com", "www.ibm.com", "careers.ibm.com")
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        query_url = f"{self.ROOT_URL}?{urlencode({'q': self._keyword_query(profile)})}"
        loc_url = f"{self.ROOT_URL}?{urlencode({'q': self._keyword_query(profile), 'location': self._location_query(profile)})}"
        return [query_url, loc_url]


__all__ = ["IBMCareersAdapter"]
