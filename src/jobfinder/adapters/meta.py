from __future__ import annotations

from urllib.parse import urlencode

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class MetaCareersAdapter(GenericPublicCareersAdapter):
    source = "meta"
    company = "Meta"

    ROOT_URL = "https://www.metacareers.com/jobsearch/"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("metacareers.com", "www.metacareers.com")
    DESCRIPTION_SELECTORS = (
        "div[data-testid='job-description']",
        "section[data-testid='job-description']",
        "div[class*='job-description']",
        "main",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        keywords = self._keyword_query(profile)
        primary_location = self._location_query(profile)

        url_a = f"{self.ROOT_URL}?{urlencode({'q': keywords, 'offices[0]': 'Europe & Middle East'})}"
        url_b = f"{self.ROOT_URL}?{urlencode({'sub_teams[0]': 'Artificial Intelligence', 'offices[0]': 'Europe & Middle East'})}"
        url_c = f"{self.ROOT_URL}?{urlencode({'q': keywords, 'offices[0]': primary_location})}"
        return [url_a, url_b, url_c]


__all__ = ["MetaCareersAdapter"]
