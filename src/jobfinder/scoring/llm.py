from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from jobfinder.models.domain import LLMFit, NormalizedJobPosting, SearchProfile

logger = logging.getLogger(__name__)


class OllamaFitScorer:
    def __init__(self, base_url: str, model: str) -> None:
        self.llm = ChatOllama(base_url=base_url, model=model, temperature=0.0)

    def score_job(self, profile: SearchProfile, job: NormalizedJobPosting) -> LLMFit:
        system = SystemMessage(
            content=(
                "You are a strict recruiter assistant. "
                "Return only valid JSON with exact keys: "
                "role_fit, research_fit, location_fit, seniority_fit, reasoning. "
                "All score fields must be numbers from 0 to 10 and reasoning must be a short string."
            )
        )
        human = HumanMessage(
            content=json.dumps(
                {
                    "profile": {
                        "target_roles": profile.target_roles,
                        "role_synonyms": profile.role_synonyms,
                        "required_skills": profile.required_skills,
                        "optional_skills": profile.optional_skills,
                        "locations": profile.locations,
                        "location_policy": profile.location_policy,
                    },
                    "job": {
                        "title": job.title,
                        "location_text": job.location_text,
                        "is_remote": job.is_remote,
                        "description_text": job.description_text[:2500],
                        "seniority": job.seniority,
                    },
                    "scale": "all fit scores are from 0 to 10",
                    "output_example": {
                        "role_fit": 7.5,
                        "research_fit": 6.0,
                        "location_fit": 9.0,
                        "seniority_fit": 7.0,
                        "reasoning": "Strong ML match, location is Madrid-compatible, seniority acceptable.",
                    },
                },
                ensure_ascii=True,
            )
        )
        try:
            response = self.llm.invoke([system, human])
            parsed = self._parse_json(response.content)
            coerced = self._coerce_fit_payload(parsed)
            return LLMFit.model_validate(coerced)
        except Exception as exc:  # pragma: no cover - runtime best effort
            logger.warning("LLM scoring failed for %s: %s", job.fingerprint(), exc)
            return LLMFit(reasoning="LLM scoring unavailable")

    def _parse_json(self, content: Any) -> dict[str, Any]:
        text = str(content)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object in model output")
        blob = text[start : end + 1]
        return json.loads(blob)

    def _coerce_fit_payload(self, parsed: dict[str, Any]) -> dict[str, Any]:
        payload = dict(parsed)
        keys = ("role_fit", "research_fit", "location_fit", "seniority_fit")

        # Common failure mode: model nests the entire payload under "reasoning".
        reasoning_obj = payload.get("reasoning")
        if isinstance(reasoning_obj, dict):
            for key in keys:
                if key not in payload and key in reasoning_obj:
                    payload[key] = reasoning_obj[key]
            payload["reasoning"] = reasoning_obj.get("reasoning") or reasoning_obj.get("summary") or json.dumps(
                reasoning_obj,
                ensure_ascii=False,
            )

        # Common variants: payload wrapped under result/data/output.
        for wrapper_key in ("result", "data", "output", "scores"):
            wrapped = payload.get(wrapper_key)
            if isinstance(wrapped, dict):
                for key in keys:
                    if key not in payload and key in wrapped:
                        payload[key] = wrapped[key]
                if "reasoning" not in payload and "reasoning" in wrapped:
                    payload["reasoning"] = wrapped["reasoning"]

        return {
            "role_fit": self._parse_score(payload.get("role_fit")),
            "research_fit": self._parse_score(payload.get("research_fit")),
            "location_fit": self._parse_score(payload.get("location_fit")),
            "seniority_fit": self._parse_score(payload.get("seniority_fit")),
            "reasoning": self._parse_reasoning(payload.get("reasoning")),
        }

    def _parse_score(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(10.0, float(value)))
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return 0.0
            ratio = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)", text)
            if ratio:
                numerator = float(ratio.group(1))
                denominator = float(ratio.group(2))
                if denominator > 0:
                    return max(0.0, min(10.0, numerator / denominator * 10.0))

            number = re.search(r"-?\d+(?:\.\d+)?", text)
            if number:
                parsed = float(number.group(0))
                # Normalize percentages or /100-style scores.
                if parsed > 10.0 and parsed <= 100.0:
                    parsed /= 10.0
                return max(0.0, min(10.0, parsed))
        return 0.0

    def _parse_reasoning(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


def llm_fit_to_score(fit: LLMFit) -> float:
    # Weighted toward role and location for this use case.
    total = fit.role_fit * 0.4 + fit.research_fit * 0.2 + fit.location_fit * 0.3 + fit.seniority_fit * 0.1
    return max(0.0, min(100.0, total * 10.0))
