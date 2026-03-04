# README & Diagram Redesign — 2026-03-04

## Goal

Redesign the three SVG diagrams and lightly trim the README for clarity and aesthetic quality.

## Visual Theme

GitHub dark palette throughout all three SVGs:

| Token | Value | Usage |
|-------|-------|-------|
| bg | #0d1117 | SVG canvas / outer background |
| surface | #161b22 | Cards and panels |
| surface-raised | #21262d | Highlighted / active cards |
| border-default | #30363d | Generic card borders |
| text-primary | #e6edf3 | Headings and body |
| text-secondary | #8b949e | Sub-labels and captions |
| accent-blue | #58a6ff | Phase A / setup |
| accent-green | #3fb950 | Phase B / scoring |
| accent-orange | #d29922 | Phase C / persistence |
| accent-purple | #bc8cff | Operational notes |
| accent-red | #f85149 | Error / failure states |

## Diagram Designs

### 1. architecture-overview.svg (1200 × 640)

Horizontal three-column flow:

- **Column 1 — Inputs**: CLI commands card, Config card (YAML + .env), Systemd timer card. Blue left border.
- **Column 2 — LangGraph Core**: Single large dark card. Rows inside: "16 Source Adapters → Normalize → Dedup", "Rule Filter → Embedding (FAISS) → LLM Score", "Rank + Select". Blue border. Ollama models sub-card below.
- **Column 3 — Outputs**: SQLite DB card, File Artifacts card, Streamlit Dashboard card. Orange border.
- Arrows: left→center→right. Ollama card arrows up into center column.

### 2. langgraph-pipeline.svg (820 × 1260)

Vertical flowchart:

- Narrow canvas to fit well inline in README.
- 12 numbered node boxes stacked vertically with connecting arrows.
- Left-side phase bracket/label for each group:
  - Phase A (blue): nodes 1–5 (setup + fetching)
  - Phase B (green): nodes 6–9 (filtering + scoring)
  - Phase C (orange): nodes 10–12 (persist + report)
- Each node: number badge (colored circle), bold name, 2–3 short detail lines.
- Footer row: "crawl_only mode" note and "failure policy" note as side annotations.

### 3. data-storage-map.svg (1200 × 680)

Two-column panels + bottom strip:

- **Left panel (SQLite)**: Relationship cards for `runs`, `run_source_status`, `profile_snapshots`, `jobs`, `job_versions`, `alerts`, `job_scores` — each as a compact dark card. FK arrows between them.
- **Right panel (Filesystem)**: Monospaced path tree for raw snapshots, FAISS index, and report files.
- **Bottom strip**: Three consumer cards — CLI (write), Streamlit (read), prune (delete).

## README Changes

- Remove "Step-by-Step: How One Run Works" (12-node prose list) — replaced by pipeline diagram.
- Remove "Data Model and Outputs" (table list + file paths) — replaced by storage map diagram.
- Collapse "Dashboard Guide" to 4–5 lines.
- Trim prose in Architecture, Scoring Model, and Known Behaviors sections.
- No sections added; no information permanently lost (all covered by diagrams).
