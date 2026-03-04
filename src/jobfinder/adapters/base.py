from __future__ import annotations

import html
import hashlib
import json
from collections.abc import Iterable
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dt_parser

from jobfinder.models.domain import NormalizedJobPosting, RawJobPosting, SearchProfile


class SourceBlockedError(RuntimeError):
    pass


class SourceAdapter(ABC):
    source: str
    company: str

    @abstractmethod
    def fetch(
        self,
        profile: SearchProfile,
        client: httpx.Client,
        browser_ctx: Any | None = None,
    ) -> list[RawJobPosting]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: RawJobPosting) -> NormalizedJobPosting:
        raise NotImplementedError

    def _safe_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = dt_parser.parse(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            return None

    def _content_hash(self, payload: dict[str, Any]) -> str:
        dumped = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    def _extract_description_from_html(
        self,
        html_text: str,
        selectors: Iterable[str] | None = None,
    ) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        selector_list = list(selectors or [])

        for selector in selector_list:
            node = soup.select_one(selector)
            if node is None:
                continue
            for tag in node.select("script,style,noscript,svg"):
                tag.decompose()
            rich = node.decode_contents().strip()
            if rich:
                return rich
            text = node.get_text("\n", strip=True)
            if text:
                return text

        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            try:
                blob = json.loads(text)
            except json.JSONDecodeError:
                continue
            entries = blob if isinstance(blob, list) else [blob]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") != "JobPosting":
                    continue
                desc = entry.get("description")
                if isinstance(desc, str) and desc.strip():
                    return html.unescape(desc).strip()

        body = soup.body or soup
        for tag in body.select("script,style,noscript,svg"):
            tag.decompose()
        text = body.get_text("\n", strip=True)
        return text.strip()
