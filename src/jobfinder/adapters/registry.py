from __future__ import annotations

from jobfinder.adapters.adobe import AdobeCareersAdapter
from jobfinder.adapters.amazon import AmazonJobsAdapter
from jobfinder.adapters.apple import AppleJobsAdapter
from jobfinder.adapters.anthropic import AnthropicAdapter
from jobfinder.adapters.greenhouse import GreenhouseAdapter
from jobfinder.adapters.google import GoogleCareersAdapter
from jobfinder.adapters.ibm import IBMCareersAdapter
from jobfinder.adapters.lever import LeverAdapter
from jobfinder.adapters.linkedin_public import LinkedInPublicAdapter
from jobfinder.adapters.meta import MetaCareersAdapter
from jobfinder.adapters.microsoft import MicrosoftCareersAdapter
from jobfinder.adapters.nvidia import NvidiaCareersAdapter
from jobfinder.adapters.openai import OpenAIAdapter
from jobfinder.adapters.runwayml import RunwayMLCareersAdapter
from jobfinder.adapters.stability_ai import StabilityAICareersAdapter
from jobfinder.adapters.workable import WorkableAdapter
from jobfinder.models.domain import SearchProfile


def build_adapters(profile: SearchProfile) -> list:
    adapters = [
        LinkedInPublicAdapter(),
        AmazonJobsAdapter(),
        MetaCareersAdapter(),
        GoogleCareersAdapter(),
        GreenhouseAdapter(),
        MicrosoftCareersAdapter(),
        AdobeCareersAdapter(),
        StabilityAICareersAdapter(),
        WorkableAdapter(),
        NvidiaCareersAdapter(),
        AppleJobsAdapter(),
        IBMCareersAdapter(),
        LeverAdapter(),
        OpenAIAdapter(),
        AnthropicAdapter(),
        RunwayMLCareersAdapter(),
    ]
    return [a for a in adapters if profile.source_enabled.get(a.source, True)]
