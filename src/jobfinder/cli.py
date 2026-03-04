from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from jobfinder.logging import configure_logging
from jobfinder.service import JobFinderService, build_runtime

app = typer.Typer(help="Local AI job finder with Ollama + LangGraph")


@app.command()
def run(
    profile: str = typer.Option("madrid_ml", "--profile", help="Search profile ID"),
    config: Path = typer.Option(Path("config/search_profiles.yaml"), "--config", help="Profile YAML path"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Run the full job-finder pipeline (crawl + score + report)."""
    configure_logging(verbose)
    runtime = build_runtime(config)
    service = JobFinderService(runtime)
    result = service.run(profile_id=profile, crawl_only=False)

    typer.echo(f"run_id={result.run_id}")
    typer.echo(f"normalized_jobs={result.total_normalized_jobs} ranked_jobs={result.total_ranked_jobs}")
    typer.echo(f"warnings={len(result.warnings)} errors={len(result.errors)}")
    if result.report_markdown_path:
        typer.echo(f"report_md={result.report_markdown_path}")
    if result.report_json_path:
        typer.echo(f"report_json={result.report_json_path}")


@app.command()
def crawl(
    profile: str = typer.Option("madrid_ml", "--profile", help="Search profile ID"),
    config: Path = typer.Option(Path("config/search_profiles.yaml"), "--config", help="Profile YAML path"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Run crawl-only mode (no semantic/LLM scoring)."""
    configure_logging(verbose)
    runtime = build_runtime(config)
    service = JobFinderService(runtime)
    result = service.run(profile_id=profile, crawl_only=True)

    typer.echo(f"crawl_run_id={result.run_id}")
    typer.echo(f"normalized_jobs={result.total_normalized_jobs}")
    if result.report_markdown_path:
        typer.echo(f"report_md={result.report_markdown_path}")


@app.command()
def report(
    profile: str = typer.Option("madrid_ml", "--profile", help="Search profile ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Specific run ID (default latest for profile)"),
    top: int = typer.Option(15, "--top", help="Number of jobs in output"),
    config: Path = typer.Option(Path("config/search_profiles.yaml"), "--config", help="Profile YAML path"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Regenerate markdown/json report from persisted DB state."""
    configure_logging(verbose)
    runtime = build_runtime(config)
    service = JobFinderService(runtime)
    md_path, json_path = service.generate_report(profile_id=profile, run_id=run_id, top_n=top)

    typer.echo(f"report_md={md_path}")
    typer.echo(f"report_json={json_path}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    config: Path = typer.Option(Path("config/search_profiles.yaml"), "--config", help="Profile YAML path"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Serve the local Streamlit dashboard."""
    configure_logging(verbose)
    build_runtime(config)
    script_path = Path(__file__).resolve().parent / "streamlit_app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script_path),
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--",
        "--config",
        str(config),
    ]

    typer.echo(f"Starting Streamlit UI at http://{host}:{port}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        typer.echo(
            f"Streamlit exited with code {result.returncode}. "
            f"If the port is busy, try: `uv run jobfinder serve --port {port + 1}`",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def prune(
    days: int = typer.Option(180, "--days", help="Retention window in days"),
    config: Path = typer.Option(Path("config/search_profiles.yaml"), "--config", help="Profile YAML path"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Prune old run data, snapshots, and reports."""
    configure_logging(verbose)
    runtime = build_runtime(config)
    service = JobFinderService(runtime)
    stats = service.prune(days=days)

    for key, value in stats.items():
        typer.echo(f"{key}={value}")


if __name__ == "__main__":
    app()
