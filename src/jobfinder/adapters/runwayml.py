from __future__ import annotations

from jobfinder.adapters.generic_public import GenericPublicCareersAdapter


class RunwayMLCareersAdapter(GenericPublicCareersAdapter):
    source = "runwayml"
    company = "Runway"

    ROOT_URL = "https://runwayml.com/careers"

    SEARCH_URLS = (ROOT_URL,)
    ALLOWED_DOMAINS = (
        "runwayml.com",
        "www.runwayml.com",
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


__all__ = ["RunwayMLCareersAdapter"]
