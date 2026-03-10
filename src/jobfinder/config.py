from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from jobfinder.models.domain import SearchProfile

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class AppSettings(BaseSettings):
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "ministral-3:14b"
    ollama_embed_model: str = "nomic-embed-text"
    request_timeout_seconds: float = 30.0
    user_agent: str = DEFAULT_USER_AGENT
    data_dir: Path = Path("data")
    db_path: Path = Path("data/jobfinder.sqlite")
    report_dir: Path = Path("data/reports")
    raw_dir: Path = Path("data/raw")
    vector_dir: Path = Path("data/index/faiss")
    retention_days: int = 180

    model_config = SettingsConfigDict(env_file=".env", env_prefix="JOBFINDER_", extra="ignore")


class ProfileConfigError(RuntimeError):
    pass


def load_profiles(config_path: Path) -> dict[str, SearchProfile]:
    if not config_path.exists():
        raise ProfileConfigError(f"Profile config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_entries = raw.get("profiles", [])
    profiles: dict[str, SearchProfile] = {}

    for entry in profile_entries:
        try:
            profile = SearchProfile.model_validate(entry)
        except ValidationError as exc:
            raise ProfileConfigError(f"Invalid profile in {config_path}: {exc}") from exc
        profiles[profile.profile_id] = profile

    if not profiles:
        raise ProfileConfigError(f"No profiles found in {config_path}")
    return profiles


def ensure_directories(settings: AppSettings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.vector_dir.mkdir(parents=True, exist_ok=True)
