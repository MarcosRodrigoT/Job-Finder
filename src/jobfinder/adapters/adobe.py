from __future__ import annotations

from urllib.parse import urlencode

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class AdobeCareersAdapter(GenericPublicCareersAdapter):
    source = "adobe"
    company = "Adobe"

    ROOT_URL = "https://careers.adobe.com/us/en/c/engineering-and-product-jobs"
    SEARCH_URL = "https://careers.adobe.com/us/en/search-results"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("careers.adobe.com", "adobe.wd5.myworkdayjobs.com")
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        keyword_url = f"{self.SEARCH_URL}?{urlencode({'keywords': self._keyword_query(profile), 'location': self._location_query(profile)})}"
        return [self.ROOT_URL, keyword_url]


__all__ = ["AdobeCareersAdapter"]
