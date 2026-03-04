# JobFinder

Local-first AI job monitoring agent built with **Ollama + LangChain/LangGraph + Streamlit + SQLite + FAISS**, managed with **uv**.

JobFinder crawls public job pages, normalizes postings into a single schema, scores relevance against your search profile (Madrid ML + Applied Research by default), and stores everything locally for reporting and dashboard review.

## What Is Implemented

- Bundle A adapters (public-only):
  - LinkedIn guest search (best effort)
  - DeepMind (Greenhouse)
  - Hugging Face (Workable)
  - Mistral (Lever)
  - OpenAI Careers (best effort; can return 403)
  - Anthropic Careers
- LangGraph workflow with 12 explicit nodes from profile load to run finalization.
- Hybrid ranking:
  - rule score
  - semantic score (Ollama embeddings + FAISS)
  - LLM fit score (Ollama chat model)
- Local persistence:
  - SQLite (`runs`, `jobs`, `job_versions`, `alerts`, `job_scores`, ...)
  - raw snapshots (`data/raw/.../*.json.gz`)
  - per-run reports (Markdown + JSON)
  - FAISS index artifacts
- Streamlit dashboard with:
  - run selection + filters
  - analytics charts
  - ranked job list (scrollable)
  - full job details and latest description snapshot
- CLI lifecycle commands:
  - `run`, `crawl`, `report`, `serve`, `prune`
- Tests for unit logic, adapter contracts, and mocked integration pipeline.

## Architecture

![Architecture Overview](docs/images/architecture-overview.svg)

![LangGraph Pipeline](docs/images/langgraph-pipeline.svg)

![Storage Map](docs/images/data-storage-map.svg)

## Project Structure

```text
.
├── config/
│   └── search_profiles.yaml
├── data/
│   ├── jobfinder.sqlite
│   ├── raw/
│   ├── reports/
│   └── index/faiss/
├── docs/images/
├── src/jobfinder/
│   ├── adapters/
│   ├── graph/
│   ├── models/
│   ├── reporting/
│   ├── scoring/
│   ├── storage/
│   ├── cli.py
│   ├── service.py
│   └── streamlit_app.py
├── systemd/
├── tests/
└── pyproject.toml
```

## Quickstart

### 1. Prerequisites

- Python 3.11+
- `uv`
- Ollama running locally

### 2. Install

```bash
cp .env.example .env
uv sync --group dev --group test
```

### 3. Pull local models

```bash
ollama serve
ollama pull ministral-3:14b
ollama pull nomic-embed-text
```

### 4. Run one full pipeline pass

```bash
uv run jobfinder run --profile madrid_ml
```

Expected output includes:

- `run_id=...`
- `normalized_jobs=... ranked_jobs=...`
- `report_md=...`
- `report_json=...`

### 5. Launch dashboard

```bash
uv run jobfinder serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

## Step-by-Step: How One Run Works

Implementation: `src/jobfinder/graph/workflow.py`

1. `load_profile`
- Loads selected profile.
- Creates `runs` row and stores profile snapshot.

2. `expand_queries`
- Expands role/location terms from profile fields.

3. `fetch_sources_parallel`
- Executes adapter fetches concurrently.
- Captures per-source status (`success`, `blocked`, `error`, `skipped`).

4. `normalize_records`
- Saves raw payload snapshot (`data/raw/...json.gz`).
- Normalizes each posting to canonical schema.

5. `deduplicate_and_upsert`
- Upserts canonical job rows and version history.
- Applies dedup/alert policy (default 90 days).

6. `rule_filter`
- Computes deterministic pre-score.
- Keeps candidate set for semantic/LLM stages.

7. `embedding_score`
- Computes semantic relevance using Ollama embedding model + FAISS.

8. `llm_fit_score`
- Calls Ollama chat model for structured fit scoring.

9. `rank_and_select`
- Combines rule + semantic + llm.
- Applies freshness bonus.
- Sorts and selects top digest jobs.

10. `persist_outputs`
- Stores source statuses + score rows.

11. `generate_digest`
- Writes report files:
  - `data/reports/YYYY-MM-DD/<run_id>.md`
  - `data/reports/YYYY-MM-DD/<run_id>.json`

12. `finalize_run_status`
- Final status logic:
  - `failed` only if all sources failed/blocked/skipped.
  - otherwise `completed`, `completed_with_warnings`, or `completed_with_errors`.

## Scoring Model

Default profile weights (`config/search_profiles.yaml`):

- `rule`: `0.35`
- `semantic`: `0.30`
- `llm`: `0.35`

Formula:

```text
total = rule*0.35 + semantic*0.30 + llm*0.35
```

Notes:

- Rule scoring emphasizes title/location/skills overlap.
- LLM fit has components: role, research, location, seniority.
- Freshness bonus is applied in ranking for recent postings.

## Configuration

### Search profiles

File: `config/search_profiles.yaml`

Default profile `madrid_ml` contains:

- target roles + synonyms
- required/optional skills
- location policy and terms
- source toggles
- scoring weights
- digest size
- dedup window

### Environment variables

File: `.env` (copy from `.env.example`)

Key variables:

- `JOBFINDER_OLLAMA_BASE_URL`
- `JOBFINDER_OLLAMA_CHAT_MODEL`
- `JOBFINDER_OLLAMA_EMBED_MODEL`
- `JOBFINDER_REQUEST_TIMEOUT_SECONDS`
- `JOBFINDER_USER_AGENT`
- `JOBFINDER_DB_PATH`
- `JOBFINDER_REPORT_DIR`
- `JOBFINDER_RAW_DIR`
- `JOBFINDER_VECTOR_DIR`
- `JOBFINDER_RETENTION_DAYS`

## CLI Reference

Run full pipeline:

```bash
uv run jobfinder run --profile madrid_ml
```

Crawl-only (no semantic/LLM scoring):

```bash
uv run jobfinder crawl --profile madrid_ml
```

Regenerate report from stored data:

```bash
uv run jobfinder report --profile madrid_ml --top 15
uv run jobfinder report --profile madrid_ml --run-id <RUN_ID> --top 30
```

Serve Streamlit dashboard:

```bash
uv run jobfinder serve --host 127.0.0.1 --port 8765
```

Prune old data:

```bash
uv run jobfinder prune --days 180
```

## Dashboard Guide

Implementation: `src/jobfinder/streamlit_app.py`

Main UI sections:

- Sidebar filters:
  - run id
  - text query (title/company/location)
  - minimum score
  - source filter
  - new alerts only
  - sort mode
- KPI row:
  - matched jobs
  - new alerts
  - median score
  - remote share
- Analytics charts:
  - source contribution
  - score distribution
- Ranked list pane (left):
  - full list in a scrollable panel
  - one-click job selection
- Detail pane (right):
  - source URL, seen timestamps, score breakdown
  - latest snapshot metadata
  - description rendered as preserved plain text or HTML

## Data Model and Outputs

### SQLite core tables

- `runs`
- `run_source_status`
- `jobs`
- `job_versions`
- `alerts`
- `job_scores`
- `profile_snapshots`

### File artifacts

- `data/raw/YYYY/MM/DD/*.json.gz`
- `data/index/faiss/<run_id>/`
- `data/reports/YYYY-MM-DD/<run_id>.md`
- `data/reports/YYYY-MM-DD/<run_id>.json`

## Testing

Run tests:

```bash
uv run --group test pytest -q
```

Coverage includes:

- query expansion
- rule scoring
- score combiner
- dedup/upsert behavior
- adapter normalization and HTML extraction
- description enrichment
- mocked end-to-end pipeline behavior

## Known Behaviors and Troubleshooting

- `POST /api/embed 404` from Ollama:
  - embedding model missing. Pull `nomic-embed-text`.
- OpenAI careers `403`:
  - expected in some regions/network setups. Adapter records warning and run continues.
- LinkedIn blocks/CAPTCHA:
  - source is marked `blocked`; run is still successful if other sources work.
- Empty descriptions in older rows:
  - re-run after adapter updates to capture richer snapshots.
- Dashboard command exits immediately:
  - usually port conflict or Streamlit startup failure; retry with another port.

## Scheduling (Optional)

Templates are included:

- `systemd/jobfinder.service`
- `systemd/jobfinder.timer`

Example user-level install:

```bash
systemctl --user daemon-reload
systemctl --user enable --now jobfinder.timer
systemctl --user list-timers | grep jobfinder
```

## Limitations

- Public pages only (no login flows).
- No anti-bot bypass.
- Source HTML/API formats can change and require adapter maintenance.
- Always verify details directly on source pages before applying.

## Roadmap Ideas

- Add additional sources (Amazon, Google, Microsoft, NVIDIA, Apple, IBM, etc.).
- Add incremental crawling and source-specific freshness tracking.
- Add export connectors (Notion/Sheets/Slack/email).
- Add per-company black/whitelist and stronger skill matching.
