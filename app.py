"""
app.py — Main Streamlit entry point for the Data Validation Tool.
Run with: streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.ai_narrator import generate_ai_report
from src.config_loader import list_clients, load_client_config
from src.data_loader import get_db
from src.validation_runner import LOGS_DIR, run_validation
from src.validators import ValidationResult

# ────────────────────────────────────────────────────────────────────────────
# Page config
# ────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AGL Data Validation Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────────────────────────────────────────────────
# Custom CSS — premium dark design
# ────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
    color: #e6edf3;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
    border-right: 1px solid #30363d;
}

[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] .stRadio label {
    color: #8b949e !important;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
}

/* ── Header ── */
.main-header {
    background: linear-gradient(135deg, #1f6feb 0%, #388bfd 50%, #58a6ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 0;
}

.sub-header {
    color: #8b949e;
    font-size: 0.9rem;
    margin-top: 0.2rem;
    margin-bottom: 1.5rem;
}

/* ── Metric cards ── */
.metric-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
    transition: transform 0.2s ease, border-color 0.2s ease;
}
.metric-card:hover { transform: translateY(-2px); border-color: #388bfd; }
.metric-card .label { color: #8b949e; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
.metric-card .value { font-size: 2rem; font-weight: 700; margin: 0.2rem 0; }
.metric-card .value.blue  { color: #58a6ff; }
.metric-card .value.green { color: #3fb950; }
.metric-card .value.red   { color: #f85149; }
.metric-card .value.yellow{ color: #d29922; }
.metric-card .value.grey  { color: #8b949e; }

/* ── Rule status badges ── */
.badge {
    display: inline-block;
    padding: 0.25rem 0.7rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-pass   { background: rgba(63,185,80,0.15); color: #3fb950; border: 1px solid rgba(63,185,80,0.3); }
.badge-fail   { background: rgba(248,81,73,0.15);  color: #f85149; border: 1px solid rgba(248,81,73,0.3); }
.badge-warn   { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid rgba(210,153,34,0.3); }
.badge-skip   { background: rgba(139,148,158,0.15);color: #8b949e; border: 1px solid rgba(139,148,158,0.3); }

/* ── Section headers ── */
.section-header {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e6edf3;
    border-bottom: 1px solid #30363d;
    padding-bottom: 0.5rem;
    margin-top: 1.5rem;
    margin-bottom: 1rem;
}

/* ── Table override ── */
.dataframe { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }

/* ── Run button ── */
.stButton > button {
    background: linear-gradient(135deg, #1f6feb 0%, #388bfd 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.6rem 1.5rem;
    width: 100%;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.85; }

/* ── AI report box ── */
.ai-report {
    background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
    border: 1px solid #30363d;
    border-left: 3px solid #388bfd;
    border-radius: 8px;
    padding: 1.5rem;
    line-height: 1.7;
}

/* ── Progress bar ── */
.progress-bar-outer {
    background: #21262d;
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
}
.progress-bar-inner {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

/* Streamlit overrides */
div[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _badge_html(status: str) -> str:
    if "PASS" in status:
        return f'<span class="badge badge-pass">{status}</span>'
    if "FAIL" in status:
        return f'<span class="badge badge-fail">{status}</span>'
    if "WARN" in status:
        return f'<span class="badge badge-warn">{status}</span>'
    return f'<span class="badge badge-skip">{status}</span>'


def _progress_bar(pct: float, color: str = "#f85149") -> str:
    width = min(pct, 100)
    return (
        f'<div class="progress-bar-outer">'
        f'<div class="progress-bar-inner" style="width:{width}%;background:{color};"></div>'
        f'</div>'
    )


def _health_score(results: list[ValidationResult]) -> int:
    active = [r for r in results if not r.skipped]
    if not active:
        return 0
    weighted = sum(r.passed / r.total_checked if r.total_checked > 0 else 1.0 for r in active)
    return round(100 * weighted / len(active))


def _donut_chart(results: list[ValidationResult]) -> go.Figure:
    active = [r for r in results if not r.skipped and r.total_checked > 0]
    total_pass = sum(r.passed for r in active)
    total_fail = sum(r.failed for r in active)

    fig = go.Figure(
        go.Pie(
            values=[total_pass, total_fail],
            labels=["Passed", "Failed"],
            hole=0.7,
            marker=dict(colors=["#3fb950", "#f85149"], line=dict(color="#0d1117", width=2)),
            textinfo="none",
            hovertemplate="%{label}: %{value:,} rows<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(font=dict(color="#e6edf3", size=12), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=10, b=10, l=10, r=10),
        height=220,
        annotations=[
            dict(
                text=f"<b>{total_pass + total_fail:,}</b><br>rows",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=14, color="#e6edf3"),
            )
        ],
    )
    return fig


# ────────────────────────────────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.4rem;font-weight:700;color:#58a6ff;margin-bottom:0.2rem;">🔍 AGL Validator</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:#8b949e;font-size:0.78rem;margin-bottom:1.5rem;">Multi-Client Data Quality Tool</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Client selector
    available_clients = list_clients()
    client_id = st.selectbox("Client", options=available_clients, format_func=str.title, key="client_sel")

    config = load_client_config(client_id)

    # Platform selector
    platform_options = {p.pf_id: f"{p.name} ({p.alias})" for p in config.active_platforms}
    selected_pf_id = st.selectbox(
        "Platform",
        options=list(platform_options.keys()),
        format_func=lambda x: platform_options[x],
        key="platform_sel",
    )

    # Data stage
    status = st.radio(
        "Data Stage",
        options=["processed", "raw"],
        index=0,
        key="status_sel",
    )

    st.markdown("---")

    run_btn = st.button("▶  Run Validation", key="run_btn", use_container_width=True)

    st.markdown("---")
    st.markdown(
        '<div style="color:#8b949e;font-size:0.72rem;">Data source: Synthetic (swap in real exports to data/ebux_pdp.parquet)</div>',
        unsafe_allow_html=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# Main content
# ────────────────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="main-header">Data Validation & Quality Report</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="sub-header">{config.client_display_name} · {platform_options.get(selected_pf_id, "—")} · <code>{status}</code> stage</div>',
    unsafe_allow_html=True,
)

# ── State management ──
if "last_results" not in st.session_state:
    st.session_state["last_results"] = None
if "last_report" not in st.session_state:
    st.session_state["last_report"] = None
if "last_log_path" not in st.session_state:
    st.session_state["last_log_path"] = None

# ── Run validation ──
if run_btn:
    with st.spinner("Loading data and running validation checks…"):
        db_con = get_db(config)
        results, log_path = run_validation(db_con, config, selected_pf_id, status)

    with st.spinner("Generating AI narrative report…"):
        platform_name = platform_options.get(selected_pf_id, str(selected_pf_id))
        ai_report = generate_ai_report(
            client=config.client_display_name,
            platform=platform_name,
            status=status,
            results=results,
        )

    st.session_state["last_results"] = results
    st.session_state["last_report"] = ai_report
    st.session_state["last_log_path"] = log_path
    st.success(f"✅ Validation complete! Audit log saved to `{log_path.name}`")


results: list[ValidationResult] | None = st.session_state["last_results"]
ai_report: str | None = st.session_state["last_report"]

if results is None:
    st.markdown(
        """
        <div style="text-align:center;padding:4rem 2rem;color:#8b949e;">
            <div style="font-size:3rem;margin-bottom:1rem;">🔍</div>
            <div style="font-size:1.1rem;font-weight:500;color:#e6edf3;">Select a client and platform, then click <strong>Run Validation</strong></div>
            <div style="font-size:0.85rem;margin-top:0.5rem;">All rule checks run in real SQL — the AI only narrates the results.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# Metric cards row
# ────────────────────────────────────────────────────────────────────────────

active_results = [r for r in results if not r.skipped]
total_rows = max((r.total_checked for r in active_results), default=0)
rules_passed = sum(1 for r in active_results if r.failed == 0)
rules_failed = sum(1 for r in active_results if r.failed > 0)
rules_skipped = sum(1 for r in results if r.skipped)
health = _health_score(results)

health_color = "green" if health >= 80 else "yellow" if health >= 60 else "red"

col1, col2, col3, col4, col5 = st.columns(5)
cards = [
    (col1, "Total Rows", f"{total_rows:,}", "blue"),
    (col2, "Health Score", f"{health}%", health_color),
    (col3, "Rules Passed", str(rules_passed), "green"),
    (col4, "Rules Failed", str(rules_failed), "red" if rules_failed > 0 else "green"),
    (col5, "Skipped", str(rules_skipped), "grey"),
]
for col, label, val, color in cards:
    with col:
        st.markdown(
            f'<div class="metric-card"><div class="label">{label}</div>'
            f'<div class="value {color}">{val}</div></div>',
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# Two-column layout: chart + rule breakdown
# ────────────────────────────────────────────────────────────────────────────

col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown('<div class="section-header">Pass / Fail Distribution</div>', unsafe_allow_html=True)
    if active_results:
        st.plotly_chart(_donut_chart(results), use_container_width=True, config={"displayModeBar": False})

with col_right:
    st.markdown('<div class="section-header">Validation Rules</div>', unsafe_allow_html=True)
    for r in results:
        badge = _badge_html(r.status)
        with st.expander(f"{r.rule_name}  —  {r.status}", expanded=(not r.skipped and r.failed > 0)):
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total Checked", f"{r.total_checked:,}")
            col_b.metric("Failed", f"{r.failed:,}")
            col_c.metric("Failure %", f"{r.failure_pct:.1f}%")

            if r.skipped:
                st.info(f"⚪ Skipped: {r.skip_reason}")
            else:
                st.markdown(f"*{r.description}*")
                if r.failure_pct > 0:
                    bar_color = "#f85149" if r.failure_pct >= 20 else "#d29922"
                    st.markdown(
                        _progress_bar(r.failure_pct, bar_color),
                        unsafe_allow_html=True,
                    )
                if r.sample_failures:
                    st.markdown("**Sample failures:**")
                    st.dataframe(
                        pd.DataFrame(r.sample_failures),
                        use_container_width=True,
                        hide_index=True,
                    )

# ────────────────────────────────────────────────────────────────────────────
# AI Report
# ────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">🤖 AI Narrative Report</div>', unsafe_allow_html=True)
if ai_report:
    with st.container():
        st.markdown(f'<div class="ai-report">', unsafe_allow_html=True)
        st.markdown(ai_report)
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Run a validation to generate the AI report.")

# ────────────────────────────────────────────────────────────────────────────
# Run history
# ────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">📋 Audit Log History</div>', unsafe_allow_html=True)

log_files = sorted(LOGS_DIR.glob("*.json"), reverse=True)
if not log_files:
    st.caption("No audit logs yet. Run a validation to create the first one.")
else:
    selected_log = st.selectbox(
        "Load a past run",
        options=[f.name for f in log_files[:20]],
        key="log_sel",
    )
    if selected_log:
        log_path = LOGS_DIR / selected_log
        with open(log_path, encoding="utf-8") as f:
            log_data = json.load(f)

        log_cols = st.columns(4)
        log_cols[0].metric("Client", log_data.get("client", "—"))
        log_cols[1].metric("Platform", log_data.get("platform", "—"))
        log_cols[2].metric("Rules Passed", log_data["summary"]["passed_rules"])
        log_cols[3].metric("Rules Failed", log_data["summary"]["failed_rules"])

        with st.expander("Full log JSON"):
            st.json(log_data)
