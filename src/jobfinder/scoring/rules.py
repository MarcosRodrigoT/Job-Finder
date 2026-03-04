from __future__ import annotations

import re

from jobfinder.models.domain import NormalizedJobPosting, SearchProfile


def _contains_any(text: str, terms: list[str]) -> int:
    score = 0
    lowered = text.lower()
    for term in terms:
        if not term:
            continue
        if re.search(rf"\b{re.escape(term.lower())}\b", lowered):
            score += 1
    return score


def rule_score_job(job: NormalizedJobPosting, profile: SearchProfile) -> tuple[float, str]:
    role_terms = [*profile.target_roles, *profile.role_synonyms]
    role_hits = _contains_any(job.title, role_terms)

    skill_hits = _contains_any(job.description_text, profile.required_skills)
    optional_hits = _contains_any(job.description_text, profile.optional_skills)

    location_text = f"{job.location_text} {'remote' if job.is_remote else ''}".lower()
    madrid_hit = "madrid" in location_text
    spain_hit = "spain" in location_text or "es" in location_text
    remote_hit = "remote" in location_text

    location_score = 0
    if madrid_hit:
        location_score = 30
    elif spain_hit and remote_hit:
        location_score = 25
    elif spain_hit:
        location_score = 15

    role_score = min(40, role_hits * 20)
    skill_score = min(20, skill_hits * 7 + optional_hits * 3)

    total = max(0.0, min(100.0, float(role_score + location_score + skill_score)))

    rationale_parts = []
    if role_hits:
        rationale_parts.append(f"role terms matched: {role_hits}")
    if madrid_hit:
        rationale_parts.append("location matches Madrid")
    elif spain_hit and remote_hit:
        rationale_parts.append("location matches Spain remote")
    elif spain_hit:
        rationale_parts.append("location matches Spain")
    if skill_hits:
        rationale_parts.append(f"required skills matched: {skill_hits}")
    if optional_hits:
        rationale_parts.append(f"optional skills matched: {optional_hits}")

    if not rationale_parts:
        rationale_parts.append("low keyword overlap")

    return total, "; ".join(rationale_parts)
