from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import orjson

from jobfinder.models.domain import RankedJob, RunResult, SourceStatus


def write_run_reports(
    report_dir: Path,
    run_result: RunResult,
    ranked_jobs: list[RankedJob],
    top_n: int,
) -> tuple[Path, Path]:
    date_folder = report_dir / datetime.now(UTC).strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)

    md_path = date_folder / f"{run_result.run_id}.md"
    json_path = date_folder / f"{run_result.run_id}.json"

    markdown = build_markdown(run_result, ranked_jobs[:top_n], top_n)
    md_path.write_text(markdown, encoding="utf-8")

    json_payload = {
        "run": run_result.model_dump(mode="json"),
        "ranked_jobs": [job.model_dump(mode="json") for job in ranked_jobs[:top_n]],
    }
    json_path.write_bytes(orjson.dumps(json_payload, option=orjson.OPT_INDENT_2))
    return md_path, json_path


def build_markdown(run_result: RunResult, top_jobs: list[RankedJob], top_n: int) -> str:
    lines = [
        f"# JobFinder Daily Digest ({run_result.run_id})",
        "",
        f"- Profile: `{run_result.profile_id}`",
        f"- Started: `{run_result.started_at.isoformat()}`",
        f"- Total normalized jobs: `{run_result.total_normalized_jobs}`",
        f"- Ranked jobs: `{run_result.total_ranked_jobs}`",
        "",
        "## Source Health",
        "",
    ]

    for status in run_result.source_statuses:
        icon = "OK"
        if status.status == SourceStatus.blocked:
            icon = "BLOCKED"
        elif status.status == SourceStatus.error:
            icon = "ERROR"
        elif status.status == SourceStatus.skipped:
            icon = "SKIPPED"

        detail = f" ({status.error})" if status.error else ""
        lines.append(
            f"- {icon} `{status.source}` fetched={status.fetched_count} normalized={status.normalized_count}{detail}"
        )

    lines.extend(["", f"## Top {top_n} Matches", ""])

    for idx, ranked in enumerate(top_jobs, start=1):
        j = ranked.job
        lines.extend(
            [
                f"### {idx}. {j.title} - {j.company}",
                f"- Score: `{ranked.score.total}` (rule `{ranked.score.rule}` / semantic `{ranked.score.semantic}` / llm `{ranked.score.llm}`)",
                f"- Location: `{j.location_text}` (remote={j.is_remote})",
                f"- Link: {j.url}",
                f"- New alert: `{ranked.is_new_alert}`",
                f"- Why this fits: {ranked.score.rationale}",
                f"- LLM analysis: {ranked.llm_fit.reasoning}",
                "",
            ]
        )

    if run_result.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend([f"- {w}" for w in run_result.warnings])
        lines.append("")

    if run_result.errors:
        lines.extend(["## Errors", ""])
        lines.extend([f"- {e}" for e in run_result.errors])
        lines.append("")

    return "\n".join(lines)
