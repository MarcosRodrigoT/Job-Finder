from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jobfinder.models.domain import RawJobPosting


class RawSnapshotStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, raw_job: RawJobPosting) -> str:
        now = datetime.now(UTC)
        folder = self.base_dir / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        folder.mkdir(parents=True, exist_ok=True)

        payload_json = json.dumps(raw_job.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        snapshot_id = f"{raw_job.source}-{digest[:16]}"
        target = folder / f"{snapshot_id}.json.gz"

        with gzip.open(target, "wt", encoding="utf-8") as f:
            f.write(payload_json)

        return snapshot_id

    def prune(self, older_than_days: int) -> int:
        cutoff = datetime.now(UTC).timestamp() - older_than_days * 86400
        removed = 0
        for file in self.base_dir.rglob("*.json.gz"):
            if file.stat().st_mtime < cutoff:
                file.unlink(missing_ok=True)
                removed += 1
        return removed
