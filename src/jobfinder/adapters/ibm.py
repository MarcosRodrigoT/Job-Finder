from __future__ import annotations

import logging

import httpx

from jobfinder.adapters.base import SourceAdapter
from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class IBMCareersAdapter(SourceAdapter):
    source = "ibm"
    company = "IBM"

    SEARCH_API_URL = "https://www-api.ibm.com/search/api/v2"
    PAGE_SIZE = 30
    MAX_PAGES = 5

    def fetch(self, profile: SearchProfile, client: httpx.Client, browser_ctx: object | None = None) -> list[RawJobPosting]:
        search_text = self._keyword_query(profile)
        all_hits = self._fetch_from_api(client, search_text)
        logger.info("IBM fetched %d raw jobs", len(all_hits))
        return self._to_raw_postings(all_hits)

    def _keyword_query(self, profile: SearchProfile) -> str:
        terms = [term.strip() for term in profile.role_terms() if term.strip()]
        if terms:
            return " ".join(terms[:5])
        return "machine learning"

    def _fetch_from_api(self, client: httpx.Client, search_text: str) -> list[dict]:
        all_hits: list[dict] = []

        for page in range(self.MAX_PAGES):
            offset = page * self.PAGE_SIZE
            body = {
                "appId": "careers",
                "scopes": ["careers2"],
                "query": {
                    "bool": {
                        "must": [{
                            "simple_query_string": {
                                "query": search_text,
                                "fields": [
                                    "keywords^1", "body^1", "url^2",
                                    "description^2", "h1s_content^2",
                                    "title^3", "field_text_01",
                                ],
                            }
                        }]
                    }
                },
                "_source": [
                    "_id", "title", "url", "description", "language",
                    "field_keyword_17", "field_keyword_08",
                    "field_keyword_18", "field_keyword_19",
                ],
                "size": self.PAGE_SIZE,
                "from": offset,
                "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
                "lang": "zz",
            }
            try:
                response = client.post(
                    self.SEARCH_API_URL,
                    json=body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            except httpx.HTTPError:
                break

            if response.status_code != 200:
                logger.info("IBM search API returned %s", response.status_code)
                break

            try:
                payload = response.json()
            except Exception:
                break

            hits_obj = payload.get("hits", {})
            hits = hits_obj.get("hits", [])
            if not hits:
                break

            all_hits.extend(hits)

            total = hits_obj.get("total", {}).get("value", 0)
            if offset + self.PAGE_SIZE >= total:
                break

        return all_hits

    def _to_raw_postings(self, hits: list[dict]) -> list[RawJobPosting]:
        postings: list[RawJobPosting] = []
        seen_urls: set[str] = set()

        for hit in hits:
            source = hit.get("_source", {})
            if not source:
                continue

            title = str(source.get("title") or "").strip()
            if not title:
                continue

            url = str(source.get("url") or "").strip()
            if not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            location = str(source.get("field_keyword_19") or "")
            work_type = str(source.get("field_keyword_17") or "")
            if work_type:
                location = f"{location}, {work_type}".strip(", ")

            description = str(source.get("description") or "").strip()

            postings.append(
                RawJobPosting(
                    source=self.source,
                    company=self.company,
                    payload={
                        "id": str(hit.get("_id") or url),
                        "title": title,
                        "location": location,
                        "url": url,
                        "posted_at": None,
                        "description": description,
                    },
                    url=url,
                )
            )

        return postings

    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        p = raw.payload
        location_text = str(p.get("location") or "")
        return NormalizedJobPosting(
            source=self.source,
            company=self.company,
            source_job_id=str(p.get("id") or p.get("url") or ""),
            url=str(p.get("url") or "https://careers.ibm.com"),
            title=str(p.get("title") or "Unknown role"),
            location_text=location_text,
            is_remote="remote" in location_text.lower(),
            posted_at=self._safe_dt(str(p.get("posted_at") or "") or None),
            description_text=str(p.get("description") or ""),
            employment_type=None,
            seniority=None,
            raw_snapshot_id="",
            content_hash=self._content_hash(dict(p)),
        )


__all__ = ["IBMCareersAdapter"]
