from __future__ import annotations

from urllib.parse import urlencode

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class NvidiaCareersAdapter(GenericPublicCareersAdapter):
    source = "nvidia"
    company = "NVIDIA"

    ROOT_URL = "https://jobs.nvidia.com/careers"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = (
        "jobs.nvidia.com",
        "nvidia.wd5.myworkdayjobs.com",
        "nvidia.com",
    )
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        params = {
            "query": self._keyword_query(profile),
            "location": self._location_query(profile),
            "sort_by": "relevance",
            "filter_include_remote": 1,
        }
        return [f"{self.ROOT_URL}?{urlencode(params)}"]


__all__ = ["NvidiaCareersAdapter"]
