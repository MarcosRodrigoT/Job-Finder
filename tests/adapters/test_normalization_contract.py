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
from jobfinder.models.domain import RawJobPosting


SAMPLE_PAYLOAD = {
    "id": "id-1",
    "title": "Machine Learning Engineer",
    "location": "Madrid, Spain",
    "url": "https://example.com/job/1",
    "posted_at": "2026-03-01T12:00:00Z",
    "description": "Work on ML systems",
}


def test_normalized_required_fields_present() -> None:
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

    for adapter in adapters:
        raw = RawJobPosting(source=adapter.source, company=adapter.company, payload=SAMPLE_PAYLOAD)
        norm = adapter.normalize(raw)
        assert norm.source
        assert norm.company
        assert norm.source_job_id
        assert str(norm.url).startswith("http")
        assert norm.title
        assert norm.location_text
        assert norm.raw_snapshot_id == ""
        assert norm.content_hash
