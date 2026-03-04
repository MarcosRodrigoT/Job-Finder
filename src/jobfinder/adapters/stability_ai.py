from __future__ import annotations

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter


class StabilityAICareersAdapter(GenericPublicCareersAdapter):
    source = "stability_ai"
    company = "Stability AI"

    ROOT_URL = "https://stability.ai/careers"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = (
        "stability.ai",
        "www.stability.ai",
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
    )
    DESCRIPTION_SELECTORS = (
        "section[class*='job-description']",
        "div[class*='job-description']",
        "main",
        "article",
    )


__all__ = ["StabilityAICareersAdapter"]
