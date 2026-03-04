from __future__ import annotations

from urllib.parse import urlencode

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter
from jobfinder.models.domain import SearchProfile


class GoogleCareersAdapter(GenericPublicCareersAdapter):
    source = "google"
    company = "Google"

    ROOT_URL = "https://www.google.com/about/careers/applications/jobs/results/"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = ("google.com", "www.google.com", "careers.google.com")
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        query = self._keyword_query(profile)
        location = self._location_query(profile)

        strict = f"\"{profile.target_roles[0] if profile.target_roles else 'AI'}\" OR \"machine learning\""

        return [
            f"{self.ROOT_URL}?{urlencode({'q': query, 'location': location})}",
            f"{self.ROOT_URL}?{urlencode({'q': strict, 'location': location})}",
        ]


__all__ = ["GoogleCareersAdapter"]
