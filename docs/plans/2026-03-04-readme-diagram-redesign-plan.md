# README & Diagram Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign all three SVG diagrams to a GitHub-dark aesthetic and trim the README for conciseness.

**Architecture:** Three standalone SVG files are rewritten from scratch using the dark palette defined in the design doc. The README is edited in place, removing sections superseded by the new diagrams and tightening prose.

**Tech Stack:** SVG (hand-written), Markdown

---

## Palette Reference (use these exact hex values throughout)

| Variable | Value |
|----------|-------|
| bg | #0d1117 |
| surface | #161b22 |
| surface-raised | #21262d |
| border-default | #30363d |
| text-primary | #e6edf3 |
| text-secondary | #8b949e |
| accent-blue | #58a6ff |
| accent-green | #3fb950 |
| accent-orange | #d29922 |
| accent-purple | #bc8cff |
| accent-red | #f85149 |

---

### Task 1: Rewrite architecture-overview.svg

**Files:**
- Overwrite: `docs/images/architecture-overview.svg`

**Step 1: Write the new SVG**

Canvas: `width="1200" height="640"`. Background rect fills entire canvas with `#0d1117`.

Layout — three vertical columns at roughly x=40, x=420, x=840. Each column is a dark panel (`fill="#161b22"`, `stroke="#30363d"`).

**Column 1 — Inputs (x=40, width=340, height=480, blue left accent bar)**

Three cards stacked inside:
- "CLI Commands" — `run · crawl · report · serve · prune`
- "Config" — `search_profiles.yaml · .env`
- "Systemd Timer" — `jobfinder.timer · daily unattended`

Each card: `fill="#21262d"`, `stroke="#30363d"`, `rx="8"`, card title in `#58a6ff`, body in `#8b949e`.

Left accent bar: 4px wide rect, `fill="#58a6ff"`, full height of column panel.

**Column 2 — LangGraph Core (x=420, width=360, height=540)**

Single dark panel. Inside, three sub-rows in monospace-ish style:
- Row 1 (blue tint header): "16 Source Adapters · Concurrent fetch"
- Row 2: "Normalize → Dedup → Rule Filter"
- Row 3 (green tint): "Embedding (FAISS)  +  LLM Fit Score"
- Row 4 (orange tint): "Rank + Select → Top N digest"

Below the main panel, a smaller Ollama card: `fill="#21262d"`, `stroke="#bc8cff"` (purple), text: "Ollama  ·  chat model  ·  embed model".

**Column 3 — Outputs (x=840, width=320, height=480, orange left accent bar)**

Three cards:
- "SQLite" — `runs · jobs · scores · alerts`
- "File Artifacts" — `raw snapshots · FAISS index · reports`
- "Streamlit Dashboard" — `jobfinder serve`

**Arrows:**
- Column 1 right edge → Column 2 left edge (horizontal, `stroke="#58a6ff"`, `stroke-width="2"`, arrowhead)
- Column 2 right edge → Column 3 left edge (horizontal, `stroke="#d29922"`)
- Ollama card top edge → Column 2 bottom (vertical dashed, `stroke="#bc8cff"`)

**Title:** "JobFinder Architecture" in `#e6edf3` 28px bold at top. Subtitle in `#8b949e` 14px.

**Step 2: Verify the file renders**

Open the SVG in a browser or image viewer. Check:
- Dark background visible
- Three columns clearly separated
- Arrows visible and correctly positioned
- All text legible (no overflow or clipping)

---

### Task 2: Rewrite langgraph-pipeline.svg

**Files:**
- Overwrite: `docs/images/langgraph-pipeline.svg`

**Step 1: Write the new SVG**

Canvas: `width="820" height="1260"`. Background `#0d1117`.

Layout: single vertical column of 12 node boxes centered around x=410. Each node box: `width="560"`, `x="130"`, variable height ~80px, `fill="#161b22"`, `stroke="#30363d"`, `rx="8"`.

Phase bracket system on the left (x=30–120):
- Phase A (nodes 1–5): vertical rect `fill="#1f3a5f"` with label "Phase A" rotated, `stroke="#58a6ff"`
- Phase B (nodes 6–9): `fill="#1a3a22"`, `stroke="#3fb950"`, label "Phase B"
- Phase C (nodes 10–12): `fill="#3a2a10"`, `stroke="#d29922"`, label "Phase C"

**Each node box contains:**
- Left colored dot/badge (circle r=10, colored per phase): blue for A, green for B, orange for C
- Node number in badge (white text)
- Node name bold `#e6edf3` 15px
- 2 detail lines `#8b949e` 12px

**Node content:**

1. `load_profile` — persist run start · snapshot profile config
2. `expand_queries` — merge roles + synonyms · append locations
3. `fetch_sources_parallel` — 16 adapters · concurrent HTTPX · per-source status
4. `normalize_records` — canonical schema · save raw .json.gz
5. `deduplicate_and_upsert` — upsert jobs/versions · 90-day dedup window
6. `rule_filter` — title/location/skill heuristics · threshold filter (35%)
7. `embedding_score` — Ollama embed + FAISS similarity (30%)
8. `llm_fit_score` — Ollama chat · role/research/location/seniority (35%)
9. `rank_and_select` — weighted composite + freshness bonus · top N
10. `persist_outputs` — save run_source_status + job_scores rows
11. `generate_digest` — write .md + .json report files
12. `finalize_run_status` — completed / warnings / errors / failed

**Connecting arrows:** short vertical arrows between consecutive nodes, centered, `stroke="#30363d"`, `stroke-width="1.5"`, small arrowhead.

**Footer (y≈1180):** Two side-by-side annotation boxes:
- "crawl_only: skips steps 7–8" with `stroke="#bc8cff"`
- "Failure: run fails only if all sources fail" with `stroke="#f85149"`

**Step 2: Verify the file renders**

Open in browser. Check:
- All 12 nodes visible without clipping
- Phase brackets clearly label node groups
- Node numbers and names readable
- Footer annotations visible

---

### Task 3: Rewrite data-storage-map.svg

**Files:**
- Overwrite: `docs/images/data-storage-map.svg`

**Step 1: Write the new SVG**

Canvas: `width="1200" height="680"`. Background `#0d1117`.

Layout:
- Left panel: x=30, y=80, width=560, height=460 — SQLite schema
- Right panel: x=620, y=80, width=550, height=460 — Filesystem
- Bottom strip: x=30, y=560, width=1140, height=100 — Consumers

**Left panel — SQLite** (`fill="#161b22"`, `stroke="#58a6ff"`, `rx="10"`):

Section title "SQLite · data/jobfinder.sqlite" in `#58a6ff`.

Seven compact table cards (2 columns × rows):
- Top row: `runs`, `run_source_status`, `profile_snapshots`
- Middle row: `jobs`, `job_versions`, `alerts`
- Bottom card spanning: `job_scores`

Each table card: `fill="#21262d"`, `stroke="#30363d"`, table name in `#e6edf3` bold, key fields in `#8b949e` 11px monospace.

FK arrows: thin dashed lines `stroke="#30363d"` connecting cards (runs→run_source_status, runs→profile_snapshots, jobs→job_versions, jobs→alerts, runs+jobs→job_scores).

**Right panel — Filesystem** (`fill="#161b22"`, `stroke="#d29922"`, `rx="10"`):

Section title "Filesystem Artifacts" in `#d29922`.

Three file-tree cards stacked:
- Raw Snapshots: `data/raw/YYYY/MM/DD/*.json.gz` — monospace `#8b949e`
- FAISS Index: `data/index/faiss/<run_id>/`
- Reports: `data/reports/YYYY-MM-DD/<run_id>.md` and `.json`

Each in a `fill="#21262d"` card with a colored left bar (raw=blue, faiss=purple, reports=orange).

**Bottom strip** (`fill="#161b22"`, `stroke="#30363d"`, `rx="8"`):

Three consumer cards side by side:
- "CLI run/crawl" → writes DB + files (`stroke="#3fb950"`)
- "Streamlit" → reads runs, scores, descriptions (`stroke="#58a6ff"`)
- "jobfinder prune" → deletes old rows + files (`stroke="#f85149"`)

Dashed arrows from panels down to consumer strip.

**Step 2: Verify the file renders**

Open in browser. Check:
- Both panels fill their space cleanly
- Table names readable
- FK arrows not overlapping text
- Consumer strip aligns with panels above

---

### Task 4: Trim the README

**Files:**
- Modify: `README.md`

**Step 1: Remove "Step-by-Step: How One Run Works"**

Delete the entire section from `## Step-by-Step: How One Run Works` through the end of step 12 (the `finalize_run_status` description), approximately lines 124–173 in the current file. This is now covered by the pipeline diagram.

**Step 2: Remove "Data Model and Outputs"**

Delete the entire `## Data Model and Outputs` section (SQLite core tables list + File artifacts list). This is covered by the storage map.

**Step 3: Collapse "Dashboard Guide"**

Replace the current Dashboard Guide section (bullet-heavy, ~25 lines) with:

```markdown
## Dashboard

```bash
uv run jobfinder serve --host 127.0.0.1 --port 8765
```

Sidebar filters: run ID, text search, min score, source, new alerts only, sort mode.
Main view: KPI row → source/score charts → ranked job list → job detail with score breakdown and description.
```

**Step 4: Tighten "Architecture" section**

Replace the three image lines with a single block that labels each diagram:

```markdown
## Architecture

| Diagram | Description |
|---------|-------------|
| ![Architecture Overview](docs/images/architecture-overview.svg) | System components and data flow |
| ![LangGraph Pipeline](docs/images/langgraph-pipeline.svg) | 12-node workflow execution |
| ![Storage Map](docs/images/data-storage-map.svg) | Database schema and file artifacts |
```

**Step 5: Tighten "Scoring Model" section**

Reduce to:

```markdown
## Scoring

`total = rule×0.35 + semantic×0.30 + llm×0.35`

- **Rule (35%):** title, location, skills heuristics
- **Semantic (30%):** Ollama embeddings + FAISS cosine similarity
- **LLM (35%):** Ollama chat model — role, research, location, seniority fit
- **Freshness bonus** applied in rank_and_select for recent postings
```

**Step 6: Read the final README and sanity-check**

Confirm:
- No orphaned section headers
- All CLI commands still present
- Diagrams still referenced
- No duplicate content

---

### Task 5: Regenerate PNG exports (optional)

**Files:**
- Overwrite: `docs/images/architecture-overview.png`
- Overwrite: `docs/images/langgraph-pipeline.png`
- Overwrite: `docs/images/data-storage-map.png`

**Step 1: Check if a rsvg-convert or Inkscape is available**

```bash
which rsvg-convert || which inkscape || which cairosvg
```

**Step 2: Export if a tool is available**

```bash
# rsvg-convert (librsvg)
rsvg-convert -w 1200 docs/images/architecture-overview.svg -o docs/images/architecture-overview.png
rsvg-convert -w 820  docs/images/langgraph-pipeline.svg    -o docs/images/langgraph-pipeline.png
rsvg-convert -w 1200 docs/images/data-storage-map.svg      -o docs/images/data-storage-map.png
```

If no tool available, skip — GitHub renders SVGs natively and the PNGs are not referenced in the README.

---

## Execution Options

Plan complete and saved to `docs/plans/2026-03-04-readme-diagram-redesign-plan.md`.

**1. Subagent-Driven (this session)** — dispatch fresh subagent per task, review between tasks

**2. Parallel Session (separate)** — open new session with executing-plans, batch execution with checkpoints
