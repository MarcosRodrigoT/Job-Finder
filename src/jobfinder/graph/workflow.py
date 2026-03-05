from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from langgraph.graph import END, START, StateGraph

from jobfinder.adapters.base import SourceAdapter, SourceBlockedError
from jobfinder.models.domain import (
    LLMFit,
    RankedJob,
    RunResult,
    SearchProfile,
    SourceRunStatus,
    SourceStatus,
)
from jobfinder.reporting import write_run_reports
from jobfinder.scoring import OllamaFitScorer, combine_scores, llm_fit_to_score, rule_score_job
from jobfinder.storage import JobRepository, RawSnapshotStore, SemanticVectorIndex

from .state import JobFinderState

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDependencies:
    adapters: list[SourceAdapter]
    repository: JobRepository
    snapshots: RawSnapshotStore
    vector_index: SemanticVectorIndex
    llm_scorer: OllamaFitScorer
    report_dir: Path
    request_timeout_seconds: float
    user_agent: str


class JobFinderWorkflow:
    def __init__(self, deps: WorkflowDependencies) -> None:
        self.deps = deps
        self.graph = self._build_graph().compile()

    def run(self, profile: SearchProfile, crawl_only: bool = False) -> RunResult:
        run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        initial_state: JobFinderState = {
            "profile": profile,
            "crawl_only": crawl_only,
            "run_result": RunResult(
                run_id=run_id,
                profile_id=profile.profile_id,
                started_at=datetime.now(UTC),
            ),
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["run_result"]

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(JobFinderState)
        graph.add_node("load_profile", self.load_profile)
        graph.add_node("expand_queries", self.expand_queries)
        graph.add_node("fetch_sources_parallel", self.fetch_sources_parallel)
        graph.add_node("normalize_records", self.normalize_records)
        graph.add_node("deduplicate_and_upsert", self.deduplicate_and_upsert)
        graph.add_node("rule_filter", self.rule_filter)
        graph.add_node("embedding_score", self.embedding_score)
        graph.add_node("llm_fit_score", self.llm_fit_score)
        graph.add_node("rank_and_select", self.rank_and_select)
        graph.add_node("persist_outputs", self.persist_outputs)
        graph.add_node("generate_digest", self.generate_digest)
        graph.add_node("finalize_run_status", self.finalize_run_status)

        graph.add_edge(START, "load_profile")
        graph.add_edge("load_profile", "expand_queries")
        graph.add_edge("expand_queries", "fetch_sources_parallel")
        graph.add_edge("fetch_sources_parallel", "normalize_records")
        graph.add_edge("normalize_records", "deduplicate_and_upsert")
        graph.add_edge("deduplicate_and_upsert", "rule_filter")
        graph.add_edge("rule_filter", "embedding_score")
        graph.add_edge("embedding_score", "llm_fit_score")
        graph.add_edge("llm_fit_score", "rank_and_select")
        graph.add_edge("rank_and_select", "persist_outputs")
        graph.add_edge("persist_outputs", "generate_digest")
        graph.add_edge("generate_digest", "finalize_run_status")
        graph.add_edge("finalize_run_status", END)

        return graph

    def load_profile(self, state: JobFinderState) -> JobFinderState:
        profile = state["profile"]
        run_result = state["run_result"]
        self.deps.repository.start_run(run_result.run_id, profile.profile_id)
        self.deps.repository.snapshot_profile(run_result.run_id, profile)

        return {
            **state,
            "query_terms": profile.role_terms(),
            "source_statuses": [],
            "raw_jobs_by_source": {},
            "normalized_jobs": [],
            "candidate_jobs": [],
            "rule_scores": {},
            "rule_rationales": {},
            "semantic_scores": {},
            "llm_fits": {},
            "ranked_jobs": [],
        }

    def expand_queries(self, state: JobFinderState) -> JobFinderState:
        profile = state["profile"]
        query_terms = list(dict.fromkeys([*profile.role_terms(), *profile.locations]))
        return {**state, "query_terms": query_terms}

    def fetch_sources_parallel(self, state: JobFinderState) -> JobFinderState:
        from jobfinder.adapters.browser import is_browser_available

        profile = state["profile"]
        run_result = state["run_result"]
        statuses: list[SourceRunStatus] = []
        raw_by_source: dict[str, list] = {}

        headers = {
            "User-Agent": self.deps.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        browser_flag = True if is_browser_available() else None

        def do_fetch(adapter: SourceAdapter) -> tuple[str, list, SourceRunStatus]:
            if not profile.source_enabled.get(adapter.source, True):
                return adapter.source, [], SourceRunStatus(source=adapter.source, status=SourceStatus.skipped)

            with httpx.Client(timeout=self.deps.request_timeout_seconds, headers=headers, follow_redirects=True) as client:
                try:
                    jobs = adapter.fetch(profile, client, browser_ctx=browser_flag)
                    status = SourceRunStatus(
                        source=adapter.source,
                        status=SourceStatus.success,
                        fetched_count=len(jobs),
                    )
                    return adapter.source, jobs, status
                except SourceBlockedError as exc:
                    status = SourceRunStatus(
                        source=adapter.source,
                        status=SourceStatus.blocked,
                        fetched_count=0,
                        error=str(exc),
                    )
                    return adapter.source, [], status
                except Exception as exc:
                    status = SourceRunStatus(
                        source=adapter.source,
                        status=SourceStatus.error,
                        fetched_count=0,
                        error=str(exc),
                    )
                    return adapter.source, [], status

        with ThreadPoolExecutor(max_workers=min(6, len(self.deps.adapters) or 1)) as pool:
            futures = [pool.submit(do_fetch, adapter) for adapter in self.deps.adapters]
            for future in as_completed(futures):
                source_name, jobs, status = future.result()
                statuses.append(status)
                raw_by_source[source_name] = jobs

        run_result.source_statuses = sorted(statuses, key=lambda s: s.source)
        run_result.total_raw_jobs = sum(len(items) for items in raw_by_source.values())

        for st in run_result.source_statuses:
            if st.status == SourceStatus.blocked and st.source == "linkedin":
                run_result.warnings.append("LinkedIn appears blocked in this run; source skipped.")
            if st.status == SourceStatus.error:
                run_result.warnings.append(f"Source {st.source} failed: {st.error}")

        return {**state, "run_result": run_result, "source_statuses": run_result.source_statuses, "raw_jobs_by_source": raw_by_source}

    def normalize_records(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]
        raw_by_source = state.get("raw_jobs_by_source", {})
        adapters = {adapter.source: adapter for adapter in self.deps.adapters}

        normalized = []
        status_map = {status.source: status for status in run_result.source_statuses}

        for source, raw_items in raw_by_source.items():
            adapter = adapters.get(source)
            if adapter is None:
                continue
            ok_count = 0
            for raw in raw_items:
                try:
                    snapshot_id = self.deps.snapshots.save(raw)
                    item = adapter.normalize(raw)
                    item.raw_snapshot_id = snapshot_id
                    normalized.append(item)
                    ok_count += 1
                except Exception as exc:
                    run_result.warnings.append(f"Normalization failed for source {source}: {exc}")
            if source in status_map:
                status_map[source].normalized_count = ok_count

        run_result.total_normalized_jobs = len(normalized)
        run_result.source_statuses = list(status_map.values())

        return {**state, "run_result": run_result, "normalized_jobs": normalized}

    def deduplicate_and_upsert(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]
        profile = state["profile"]
        normalized = state.get("normalized_jobs", [])

        job_map = self.deps.repository.upsert_jobs(
            run_id=run_result.run_id,
            jobs=normalized,
            dedup_days=profile.dedup_days,
        )
        return {**state, "job_map": job_map}

    def rule_filter(self, state: JobFinderState) -> JobFinderState:
        profile = state["profile"]
        normalized = state.get("normalized_jobs", [])

        rule_scores: dict[str, float] = {}
        rationales: dict[str, str] = {}
        candidates = []

        for job in normalized:
            score, rationale = rule_score_job(job, profile)
            fp = job.fingerprint()
            rule_scores[fp] = score
            rationales[fp] = rationale
            if score >= 10.0:
                candidates.append(job)

        if not candidates:
            candidates = normalized

        return {
            **state,
            "rule_scores": rule_scores,
            "rule_rationales": rationales,
            "candidate_jobs": candidates,
        }

    def embedding_score(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]
        profile = state["profile"]
        jobs = state.get("candidate_jobs", [])

        if state.get("crawl_only", False):
            scores = {job.fingerprint(): 0.0 for job in jobs}
        else:
            scores = self.deps.vector_index.score_jobs(run_result.run_id, profile, jobs)
        return {**state, "semantic_scores": scores}

    def llm_fit_score(self, state: JobFinderState) -> JobFinderState:
        profile = state["profile"]
        jobs = state.get("candidate_jobs", [])

        llm_scores: dict[str, LLMFit] = {}
        if state.get("crawl_only", False):
            return {**state, "llm_fits": {job.fingerprint(): LLMFit(reasoning="crawl-only mode") for job in jobs}}

        for job in jobs:
            llm_scores[job.fingerprint()] = self.deps.llm_scorer.score_job(profile, job)

        return {**state, "llm_fits": llm_scores}

    def rank_and_select(self, state: JobFinderState) -> JobFinderState:
        profile = state["profile"]
        run_result = state["run_result"]

        candidates = state.get("candidate_jobs", [])
        rule_scores = state.get("rule_scores", {})
        rule_rationales = state.get("rule_rationales", {})
        semantic_scores = state.get("semantic_scores", {})
        llm_fits = state.get("llm_fits", {})
        job_map = state.get("job_map", {})

        ranked: list[RankedJob] = []
        for job in candidates:
            fp = job.fingerprint()
            rule_score = rule_scores.get(fp, 0.0)
            semantic_score = semantic_scores.get(fp, 0.0)
            fit = llm_fits.get(fp, LLMFit(reasoning="not scored"))
            llm_score = llm_fit_to_score(fit)

            if job.posted_at is not None:
                age_days = (datetime.now(UTC) - job.posted_at).days
                freshness_bonus = max(0.0, 10.0 - age_days * 0.2)
            else:
                freshness_bonus = 0.0

            score = combine_scores(
                rule_score=rule_score,
                semantic_score=semantic_score,
                llm_score=min(100.0, llm_score + freshness_bonus),
                weights=profile.scoring_weights,
                rationale=rule_rationales.get(fp, ""),
            )

            _, is_new_alert = job_map.get(fp, (0, False))
            ranked.append(
                RankedJob(
                    job=job,
                    score=score,
                    llm_fit=fit,
                    is_new_alert=is_new_alert,
                )
            )

        ranked.sort(
            key=lambda item: (
                item.score.total,
                item.llm_fit.role_fit,
                item.llm_fit.location_fit,
                item.job.posted_at or datetime(1970, 1, 1, tzinfo=UTC),
            ),
            reverse=True,
        )

        run_result.total_ranked_jobs = len(ranked)
        run_result.top_jobs = ranked[: profile.digest_size]
        return {**state, "run_result": run_result, "ranked_jobs": ranked}

    def persist_outputs(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]
        statuses = state.get("source_statuses", run_result.source_statuses)
        ranked_jobs = state.get("ranked_jobs", [])
        job_map = state.get("job_map", {})

        self.deps.repository.save_source_statuses(run_result.run_id, statuses)
        self.deps.repository.save_scores(run_result.run_id, ranked_jobs, job_map)
        return state

    def generate_digest(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]
        profile = state["profile"]
        ranked_jobs = state.get("ranked_jobs", [])

        md_path, json_path = write_run_reports(
            report_dir=self.deps.report_dir,
            run_result=run_result,
            ranked_jobs=ranked_jobs,
            top_n=profile.digest_size,
        )
        run_result.report_markdown_path = str(md_path)
        run_result.report_json_path = str(json_path)
        return {**state, "run_result": run_result}

    def finalize_run_status(self, state: JobFinderState) -> JobFinderState:
        run_result = state["run_result"]

        run_result.completed_at = datetime.now(UTC)
        statuses = run_result.source_statuses
        successful_sources = [s for s in statuses if s.status == SourceStatus.success]
        if not successful_sources:
            final_status = "failed"
            run_result.errors.append("All sources failed or were blocked/skipped")
        elif run_result.errors:
            final_status = "completed_with_errors"
        elif run_result.warnings:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"

        self.deps.repository.complete_run(
            run_id=run_result.run_id,
            status=final_status,
            warnings=len(run_result.warnings),
            errors=len(run_result.errors),
        )
        return {**state, "run_result": run_result}
