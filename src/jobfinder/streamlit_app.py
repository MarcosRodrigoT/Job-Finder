from __future__ import annotations

import argparse
import html
import re
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import streamlit as st
from bs4 import BeautifulSoup

from jobfinder.config import AppSettings, ensure_directories
from jobfinder.storage import JobRepository

try:
    import altair as alt
except Exception:  # pragma: no cover - optional runtime dependency through streamlit
    alt = None  # type: ignore[assignment]

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional runtime dependency through streamlit
    pd = None  # type: ignore[assignment]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default="config/search_profiles.yaml")
    return parser.parse_known_args(sys.argv[1:])[0]


def _contains_html(text: str) -> bool:
    return bool(re.search(r"<\s*[a-zA-Z][^>]*>", text))


def _fmt_dt(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    raw = str(value).strip()
    if not raw:
        return "None"

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    if "." in raw:
        raw = raw.split(".", 1)[0]
    if "T" in raw:
        raw = raw.replace("T", " ")
    return raw


def _score_emoji(score: float) -> str:
    if score >= 85:
        return "🔥"
    if score >= 70:
        return "✨"
    if score >= 55:
        return "👍"
    return "🧪"


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
          :root {
            --ink: #11263b;
            --muted: #4d6278;
            --card: #ffffff;
            --line: #d5deea;
            --brand-a: #ff7f50;
            --brand-b: #2a9d8f;
            --brand-c: #264653;
          }

          .stApp {
            background:
              radial-gradient(circle at 15% 10%, #ffe9dc 0%, transparent 36%),
              radial-gradient(circle at 80% 5%, #dcfff9 0%, transparent 35%),
              linear-gradient(160deg, #f7f9fc 0%, #e8eff7 100%);
            color: var(--ink);
          }

          .hero {
            background: linear-gradient(120deg, var(--brand-a) 0%, var(--brand-b) 48%, var(--brand-c) 100%);
            border-radius: 18px;
            color: #fff;
            padding: 18px 20px;
            border: 1px solid rgba(255,255,255,0.35);
            box-shadow: 0 10px 30px rgba(39, 69, 102, 0.16);
            margin-bottom: 10px;
          }
          .hero h1 { margin: 0; font-size: 1.68rem; }
          .hero p { margin: 6px 0 0 0; opacity: 0.95; }

          .kpi-plain {
            color: #111111;
            padding: 2px 0 6px 0;
          }
          .kpi-plain .kpi-label {
            color: #111111;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 2px;
          }
          .kpi-plain .kpi-value {
            color: #111111;
            font-size: 1.58rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 2px;
          }
          .kpi-plain .kpi-sub {
            color: #111111;
            font-size: 0.9rem;
            font-weight: 500;
          }

          div.stButton > button {
            background: linear-gradient(130deg, #2a9d8f 0%, #2d7ea3 100%);
            color: #ffffff !important;
            border: 1px solid #2b7f8a;
            border-radius: 10px;
            font-weight: 650;
            box-shadow: 0 4px 12px rgba(35, 90, 120, 0.25);
            transition: all 0.18s ease;
          }
          div.stButton > button:hover {
            background: linear-gradient(130deg, #23897c 0%, #2a6f8d 100%);
            color: #ffffff !important;
            border-color: #1f647f;
            transform: translateY(-1px);
          }
          div.stButton > button:focus {
            color: #ffffff !important;
            border-color: #1f647f;
            box-shadow: 0 0 0 0.15rem rgba(42, 157, 143, 0.22);
          }

          .job-card {
            background: var(--card);
            border: 1px solid var(--line);
            border-left: 6px solid #2a9d8f;
            border-radius: 14px;
            padding: 12px 12px 10px 12px;
            margin-bottom: 10px;
            box-shadow: 0 6px 16px rgba(22, 46, 75, 0.06);
          }
          .job-card h4 {
            margin: 0 0 6px 0;
            color: #173a5b;
            line-height: 1.3;
            font-size: 1.01rem;
          }
          .job-card .meta {
            color: var(--muted);
            font-size: 0.90rem;
          }

          .desc-shell {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 14px;
            line-height: 1.5;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
          }
          .desc-pre {
            white-space: pre-wrap;
            font-family: ui-sans-serif, "Segoe UI", sans-serif;
            line-height: 1.5;
          }
          .desc-html ul, .desc-html ol {
            margin-top: 0.4rem;
            margin-bottom: 0.8rem;
          }
          .desc-html p {
            margin-top: 0.4rem;
            margin-bottom: 0.8rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def _build_repository(db_path: str) -> JobRepository:
    repo = JobRepository(Path(db_path))
    repo.init_db()
    return repo


def _html_unescape_deep(text: str, rounds: int = 3) -> str:
    current = text
    for _ in range(rounds):
        unescaped = html.unescape(current)
        if unescaped == current:
            break
        current = unescaped
    return current


def _clean_html_description(markup: str) -> str:
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup.select("script,style,noscript,svg,iframe"):
        tag.decompose()

    selectors = [
        "[data-autom='job-description']",
        "[data-testid='job-description']",
        "section[id*='job-description']",
        "div[id*='job-description']",
        "section[class*='job-description']",
        "div[class*='job-description']",
        "article",
        "main",
    ]

    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        for tag in node.select("script,style,noscript,svg,iframe,header,footer,nav,aside"):
            tag.decompose()
        candidate = node.decode_contents().strip()
        if len(BeautifulSoup(candidate, "html.parser").get_text(" ", strip=True).split()) >= 20:
            return candidate

    for tag in soup.select("header,footer,nav,aside,form,button"):
        tag.decompose()
    return soup.decode_contents().strip()


def _clean_plain_description(text: str, source: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    if source == "apple":
        markers = (
            "Shop and Learn",
            "Apple Footer",
            "Privacy Policy",
            "Terms of Use",
            "Site Map",
            "Apple Store",
            "Copyright",
            "United States",
        )
        nav_exact = {
            "apple",
            "store",
            "mac",
            "ipad",
            "iphone",
            "watch",
            "vision",
            "airpods",
            "tv & home",
            "entertainment",
            "accessories",
            "support",
            "careers at apple",
            "work at apple",
            "life at apple",
            "profile",
            "sign in",
            "search",
        }
        filtered = [
            line
            for line in lines
            if (
                not any(marker.lower() in line.lower() for marker in markers)
                and line.strip().lower() not in nav_exact
            )
        ]
        if filtered:
            lines = filtered
        else:
            return ""

    compact: list[str] = []
    for line in lines:
        if compact and line == compact[-1]:
            continue
        compact.append(line)
    return "\n".join(compact)


def _prepare_description(description_text: str, source: str) -> tuple[str, bool]:
    raw = description_text.strip()
    if not raw:
        return "", False

    unescaped = _html_unescape_deep(raw).strip()
    if not unescaped:
        return "", False

    if _contains_html(unescaped):
        cleaned_markup = _clean_html_description(unescaped)
        if cleaned_markup:
            return cleaned_markup, True

    cleaned_text = _clean_plain_description(unescaped, source)
    return cleaned_text, False


def _render_description(description_text: str, source: str) -> None:
    prepared, is_html = _prepare_description(description_text, source)
    if not prepared:
        st.info("No description available for this job snapshot yet.")
        return

    if is_html:
        st.markdown(f"<div class='desc-shell desc-html'>{prepared}</div>", unsafe_allow_html=True)
    else:
        escaped = html.escape(prepared)
        st.markdown(f"<div class='desc-shell desc-pre'>{escaped}</div>", unsafe_allow_html=True)


def _score_buckets(scores: list[float]) -> list[tuple[str, int]]:
    buckets = {
        "90-100": 0,
        "80-89": 0,
        "70-79": 0,
        "60-69": 0,
        "<60": 0,
    }
    for score in scores:
        if score >= 90:
            buckets["90-100"] += 1
        elif score >= 80:
            buckets["80-89"] += 1
        elif score >= 70:
            buckets["70-79"] += 1
        elif score >= 60:
            buckets["60-69"] += 1
        else:
            buckets["<60"] += 1
    return list(buckets.items())


def _scroll_container(height: int):
    try:
        return st.container(height=height)
    except TypeError:
        return st.container()


def _source_contribution_chart(source_counts: Counter[str]) -> None:
    st.markdown("#### 📊 Source Contribution")
    if not source_counts:
        st.info("No source data for current filters.")
        return

    if alt is None or pd is None:
        for source, count in source_counts.most_common():
            st.write(f"**{source}** · {count}")
        return

    rows = [{"source": source, "count": count} for source, count in source_counts.items()]
    df = pd.DataFrame(rows)
    palette = [
        "#0EA5A4",
        "#3B82F6",
        "#F59E0B",
        "#EF4444",
        "#8B5CF6",
        "#10B981",
        "#F97316",
        "#06B6D4",
        "#84CC16",
        "#EC4899",
    ]
    chart = (
        alt.Chart(df)
        .mark_arc(innerRadius=60, outerRadius=110)
        .encode(
            theta=alt.Theta("count:Q"),
            color=alt.Color(
                "source:N",
                legend=alt.Legend(title="Source", orient="right"),
                scale=alt.Scale(range=palette),
            ),
            tooltip=[
                alt.Tooltip("source:N", title="Source"),
                alt.Tooltip("count:Q", title="Jobs"),
            ],
        )
        .properties(height=300)
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_axis(labelColor="#24415D", titleColor="#24415D", gridColor="#D6E4F2")
        .configure_legend(labelColor="#24415D", titleColor="#24415D")
    )
    st.altair_chart(chart, width='stretch')


def _score_distribution_chart(scores: list[float]) -> None:
    st.markdown("#### 🎚️ Score Distribution")
    if not scores:
        st.info("No score data for current filters.")
        return

    buckets = _score_buckets(scores)
    if alt is None or pd is None:
        for label, count in buckets:
            st.write(f"{label}: {count}")
        return

    rows = [{"bucket": label, "count": count, "order": i} for i, (label, count) in enumerate(buckets)]
    df = pd.DataFrame(rows)
    chart = (
        alt.Chart(df)
        .mark_area(
            line={"color": "#2563EB", "strokeWidth": 2.5},
            color="#7DD3FC",
            opacity=0.58,
            interpolate="monotone",
        )
        .encode(
            x=alt.X("bucket:N", sort=[row["bucket"] for row in rows], title="Score range"),
            y=alt.Y("count:Q", title="Jobs"),
            tooltip=[
                alt.Tooltip("bucket:N", title="Range"),
                alt.Tooltip("count:Q", title="Jobs"),
            ],
        )
        .properties(height=300)
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_axis(labelColor="#24415D", titleColor="#24415D", gridColor="#D6E4F2")
        .configure_legend(labelColor="#24415D", titleColor="#24415D")
    )
    st.altair_chart(chart, width='stretch')


def main() -> None:
    args = _parse_args()

    st.set_page_config(page_title="JobFinder", page_icon="🧭", layout="wide")
    _inject_theme()

    settings = AppSettings()
    ensure_directories(settings)
    repository = _build_repository(str(settings.db_path))

    runs = repository.list_runs(limit=200)

    st.markdown(
        """
        <div class="hero">
          <h1>🧭 JobFinder Intelligence Dashboard</h1>
          <p>Find high-signal opportunities faster with ranking, source health, and detailed posting context.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not runs:
        st.warning("No runs found yet. Execute: `uv run jobfinder run --profile madrid_ml`")
        return

    selected_run = runs[0].id

    with st.sidebar:
        st.header("⚙️ Control Panel")
        query = st.text_input("🔎 Search title/company/location", "")
        min_score = st.slider("🎯 Minimum score", 0.0, 100.0, 0.0, 0.5)
        only_new = st.checkbox("🚨 Only new alerts", value=False)
        sort_mode = st.selectbox("↕️ Sort by", ["Score (high to low)", "Company (A-Z)", "Title (A-Z)"])

    ranked_rows = repository.get_ranked_jobs(selected_run, limit=700)

    sources = sorted({str(row["source"]) for row in ranked_rows})
    with st.sidebar:
        with st.expander("🛰️ Sources", expanded=True):
            selected_sources = [src for src in sources if st.checkbox(src, value=True, key=f"src_{src}")]

    filtered = []
    needle = query.strip().lower()
    for row in ranked_rows:
        total_score = float(row["total_score"])
        if total_score < min_score:
            continue
        if only_new and not bool(row["is_new_alert"]):
            continue
        if selected_sources and str(row["source"]) not in selected_sources:
            continue
        hay = f"{row['title']} {row['company']} {row['location_text']}".lower()
        if needle and needle not in hay:
            continue
        filtered.append(row)

    if sort_mode == "Company (A-Z)":
        filtered.sort(key=lambda r: str(r["company"]).lower())
    elif sort_mode == "Title (A-Z)":
        filtered.sort(key=lambda r: str(r["title"]).lower())
    else:
        filtered.sort(key=lambda r: float(r["total_score"]), reverse=True)

    scores = [float(row["total_score"]) for row in filtered]
    new_count = sum(1 for row in filtered if bool(row["is_new_alert"]))
    remote_count = sum(1 for row in filtered if bool(row["is_remote"]))
    median_score = statistics.median(scores) if scores else 0.0
    remote_ratio = (remote_count / len(filtered) * 100.0) if filtered else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(
        (
            "<div class='kpi-plain'>"
            "<div class='kpi-label'>📌 Matched Jobs</div>"
            f"<div class='kpi-value'>{len(filtered)}</div>"
            f"<div class='kpi-sub'>from {len(ranked_rows)} ranked</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    m2.markdown(
        (
            "<div class='kpi-plain'>"
            "<div class='kpi-label'>🚨 New Alerts</div>"
            f"<div class='kpi-value'>{new_count}</div>"
            f"<div class='kpi-sub'>{(new_count/len(filtered)*100.0 if filtered else 0.0):.1f}% of filtered</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    m3.markdown(
        (
            "<div class='kpi-plain'>"
            "<div class='kpi-label'>📈 Median Score</div>"
            f"<div class='kpi-value'>{median_score:.1f}</div>"
            "<div class='kpi-sub'>&nbsp;</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    m4.markdown(
        (
            "<div class='kpi-plain'>"
            "<div class='kpi-label'>🌍 Remote Share</div>"
            f"<div class='kpi-value'>{remote_ratio:.1f}%</div>"
            "<div class='kpi-sub'>&nbsp;</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    analytics_left, analytics_right = st.columns(2, gap="large")
    source_counts = Counter(str(row["source"]) for row in filtered)

    with analytics_left:
        _source_contribution_chart(source_counts)

    with analytics_right:
        _score_distribution_chart(scores)

    if not filtered:
        st.info("No jobs match the selected filters.")
        return

    if "selected_job_id" not in st.session_state:
        st.session_state.selected_job_id = int(filtered[0]["job_id"])

    left, right = st.columns([1.2, 1.8], gap="large")

    with left:
        st.subheader("🗂️ Ranked Jobs")
        with _scroll_container(1520):
            for idx, row in enumerate(filtered, start=1):
                job_id = int(row["job_id"])
                score = float(row["total_score"])
                emoji = _score_emoji(score)
                alert_icon = "🚨" if bool(row["is_new_alert"]) else "🕘"

                st.markdown(
                    (
                        "<div class='job-card'>"
                        f"<h4>{emoji} {idx}. {html.escape(str(row['title']))}</h4>"
                        f"<div class='meta'>🏢 {html.escape(str(row['company']))} | 📍 {html.escape(str(row['location_text']))}</div>"
                        f"<div class='meta'>🎯 {score:.2f} | {alert_icon}</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                if st.button("👁️ View Details", key=f"open-job-{job_id}", width='stretch'):
                    st.session_state.selected_job_id = job_id

    with right:
        selected_job_id = int(st.session_state.selected_job_id)
        selected_row = next((r for r in filtered if int(r["job_id"]) == selected_job_id), None)
        if selected_row is None:
            selected_row = filtered[0]
            selected_job_id = int(selected_row["job_id"])
            st.session_state.selected_job_id = selected_job_id

        job = repository.get_job(selected_job_id)
        version = repository.get_latest_job_version(selected_job_id)

        if job is None:
            st.error("Selected job no longer exists in DB.")
            return

        st.subheader(f"🧾 {job.title}")
        st.caption(f"🏢 {job.company} · 📍 {job.location_text}")

        st.markdown(
            f"[🔗 Open Source Link]({job.url}) · via `{job.source}` · "
            f"first seen **{_fmt_dt(job.first_seen_at)}** · last seen **{_fmt_dt(job.last_seen_at)}**"
        )

        if selected_row is not None:
            st.markdown(
                f"🎯 **{float(selected_row['total_score']):.2f}** "
                f"(rule: **{float(selected_row['rule_score']):.2f}** · "
                f"semantic: **{float(selected_row['semantic_score']):.2f}** · "
                f"llm: **{float(selected_row['llm_score']):.2f}**)"
            )

        st.markdown("### 📄 Latest Snapshot")
        if version is None:
            st.info("No version snapshot found.")
            return

        st.write(f"🗓️ Posted at: {_fmt_dt(version.posted_at)}")
        _render_description(version.description_text or "", job.source)


if __name__ == "__main__":
    main()
