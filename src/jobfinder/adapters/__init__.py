"""Job source adapters."""

from .adobe import AdobeCareersAdapter
from .amazon import AmazonJobsAdapter
from .apple import AppleJobsAdapter
from .anthropic import AnthropicAdapter
from .greenhouse import GreenhouseAdapter
from .google import GoogleCareersAdapter
from .ibm import IBMCareersAdapter
from .lever import LeverAdapter
from .linkedin_public import LinkedInPublicAdapter
from .meta import MetaCareersAdapter
from .microsoft import MicrosoftCareersAdapter
from .nvidia import NvidiaCareersAdapter
from .openai import OpenAIAdapter
from .runwayml import RunwayMLCareersAdapter
from .stability_ai import StabilityAICareersAdapter
from .workable import WorkableAdapter

__all__ = [
    "AdobeCareersAdapter",
    "AmazonJobsAdapter",
    "AppleJobsAdapter",
    "AnthropicAdapter",
    "GreenhouseAdapter",
    "GoogleCareersAdapter",
    "IBMCareersAdapter",
    "LeverAdapter",
    "LinkedInPublicAdapter",
    "MetaCareersAdapter",
    "MicrosoftCareersAdapter",
    "NvidiaCareersAdapter",
    "OpenAIAdapter",
    "RunwayMLCareersAdapter",
    "StabilityAICareersAdapter",
    "WorkableAdapter",
]
