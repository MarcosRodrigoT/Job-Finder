from __future__ import annotations

from jobfinder.adapters.anthropic import AnthropicAdapter
from jobfinder.adapters.greenhouse import GreenhouseAdapter
from jobfinder.adapters.lever import LeverAdapter
from jobfinder.adapters.linkedin_public import LinkedInPublicAdapter
from jobfinder.adapters.openai import OpenAIAdapter
from jobfinder.adapters.workable import WorkableAdapter
from jobfinder.models.domain import SearchProfile


def build_adapters(profile: SearchProfile) -> list:
    adapters = [
        LinkedInPublicAdapter(),
        GreenhouseAdapter(),
        WorkableAdapter(),
        LeverAdapter(),
        OpenAIAdapter(),
        AnthropicAdapter(),
    ]
    return [a for a in adapters if profile.source_enabled.get(a.source, True)]
