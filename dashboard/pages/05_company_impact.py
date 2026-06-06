"""
SignalScout — Company Impact Analysis
Estimated compliance exposure by company and bill, with Bill View and Company View.
"""
import os
from collections import defaultdict

import httpx
import pandas as pd
import streamlit as st

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from styles import inject_shared_styles

st.set_page_config(page_title="SignalScout — Company Impact", page_icon="🔭", layout="wide")

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

inject_shared_styles()
st.markdown("""
<style>
/* Demo banner */
.demo-banner {
    background: linear-gradient(90deg, #422006, #78350f);
    border: 1px solid #d97706;
    border-radius: 10px;
    padding: 0.75rem 1.25rem;
    margin-bottom: 1.5rem;
    color: #fde68a;
    font-weight: 600;
    font-size: 0.95rem;
}

/* Score badges */
.score-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.8rem; font-weight: 600;
}
.score-green  { background: #052e16; color: #6ee7b7; }
.score-yellow { background: #422006; color: #fbbf24; }
.score-red    { background: #450a0a; color: #fca5a5; }

/* Material tags */
.material-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 500;
    background: #1e3a5f; color: #93c5fd; margin: 2px;
}

/* Company metadata card */
.company-card {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
}
.company-card .co-name { color: #f3f4f6; font-size: 1.25rem; font-weight: 700; margin-bottom: 0.3rem; }
.company-card .co-meta { color: #6b7280; font-size: 0.82rem; }
.company-card .co-meta span { margin-right: 1.25rem; }

/* Bill row in company view */
.bill-row {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 8px;
    padding: 0.75rem 1.25rem;
    margin-bottom: 0.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.bill-row .bill-label { color: #d1d5db; font-size: 0.92rem; flex: 1; }
.bill-row .bill-cost { color: #6ee7b7; font-size: 1rem; font-weight: 600; min-width: 90px; text-align: right; display: flex; align-items: center; justify-content: flex-end; gap: 4px; }
.bill-row .bill-conf { color: #6b7280; font-size: 0.875rem; min-width: 60px; text-align: right; }

/* Fee basis badges */
.fee-badge { display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 0.68rem; font-weight: 500; white-space: nowrap; }
.fee-badge.benchmark { background: #1c1917; color: #78716c; border: 1px solid #292524; }
.fee-badge.range { background: #1c2433; color: #6b90b8; border: 1px solid #1e3a5f; }
.fee-badge.category { background: #1c1810; color: #a07040; border: 1px solid #3d2e10; }
</style>
""", unsafe_allow_html=True)


# —— Utilities ————————————————————————————————————————————————


def format_cost(value) -> str:
    if value is None or value == 0:
        return "—"
    v = float(value)
    if v >= 1_000_000_000:
        s = f"{v / 1_000_000_000:.1f}B"
        return f"${s.replace('.0B', 'B')}"
    if v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}M"
        return f"${s.replace('.0M', 'M')}"
    if v >= 1_000:
        s = f"{v / 1_000:.1f}K"
        return f"${s.replace('.0K', 'K')}"
    return f"${v:,.0f}"


def score_badge_html(score) -> str:
    if score is None:
        return '<span class="score-badge score-yellow">—</span>'
    s = int(score)
    if s <= 33:
        cls = "score-green"
    elif s <= 66:
        cls = "score-yellow"
    else:
        cls = "score-red"
    return f'<span class="score-badge {cls}">{s}</span>'


def confidence_pct(value) -> str:
    if value is None:
        return "—"
    return f"{int(float(value) * 100)}%"


def material_tag_html(category: str) -> str:
    label = category.replace("_", " ").title()
    return f'<span class="material-tag">{label}</span>'


def fee_basis_badge_html(fee_basis: str | None) -> str:
    """Return an HTML badge for non-published fee estimates; empty string for real data."""
    if not fee_basis:
        return ""
    if fee_basis == "published_range_midpoint":
        return '<span class="fee-badge range">~Midpoint</span>'
    if fee_basis == "industry_benchmark":
        return '<span class="fee-badge benchmark">~Est.</span>'
    if fee_basis == "category_benchmark":
        return '<span class="fee-badge category">~Benchmark</span>'
    return ""


_PENDING_FEE_BASES = {"published_range_midpoint", "industry_benchmark", "category_benchmark"}


# —— Cached fetchers ——————————————————————————————————————————

@st.cache_data(ttl=300)
def fetch_epr_bills() -> list:
    try:
        resp = httpx.get(
            f"{API_BASE}/bills",
            params={"epr_relevant": True, "limit": 500},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch bills: {e}")
        return []


@st.cache_data(ttl=300)
def fetch_bill_exposure(bill_id: str, limit: int = 50) -> list:
    try:
        resp = httpx.get(
            f"{API_BASE}/bills/{bill_id}/company-exposure",
            params={"limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_companies(hq_state: str | None = None) -> list:
    try:
        params = {"limit": 500}
        if hq_state:
            params["hq_state"] = hq_state
        resp = httpx.get(f"{API_BASE}/companies", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_company_detail(company_id: str) -> dict | None:
    try:
        resp = httpx.get(f"{API_BASE}/companies/{company_id}", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def fetch_company_impact_scores(company_id: str) -> list:
    try:
        resp = httpx.get(f"{API_BASE}/companies/{company_id}/impact-scores", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_exposure_brief(company_id: str, bill_id) -> dict | None:
    """Fetch (or generate) an Exposure Brief for a (company, bill) pair.
    Returns None if interpretation is disabled (503) or on any error.
    """
    try:
        resp = httpx.get(
            f"{API_BASE}/companies/{company_id}/exposure-brief",
            params={"bill_id": bill_id},
            timeout=30,
        )
        if resp.status_code == 503:
            return None  # feature flag off
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# —— Bootstrap ————————————————————————————————————————————————

all_bills = fetch_epr_bills()

if not all_bills:
    st.warning("No bills loaded. Check API connection.")
    st.stop()

bill_by_id = {b["id"]: b for b in all_bills}

# —— Demo banner ————————————————————————————————————————————
if DEMO_MODE:
    st.markdown(
        '<div class="demo-banner">🎯 Oregon Demo Mode — filtered to Oregon EPR bills</div>',
        unsafe_allow_html=True,
    )

# —— Page header ————————————————————————————————————————————
st.title("🏭 Company Impact Analysis")
st.caption("Estimated compliance exposure ranked by company and bill.")


# Pre-compute bill options (needed in both tabs)
bill_options = [b for b in all_bills if not DEMO_MODE or b.get("state") == "OR"]
if not bill_options:
    bill_options = all_bills

bill_labels = {
    b["id"]: f"{b.get('state', '??')} {b.get('bill_number', '')} — {(b.get('title') or '')[:45]}"
    for b in bill_options
}

default_idx = 0
if DEMO_MODE:
    or_ids = [b["id"] for b in bill_options if b.get("state") == "OR"]
    if or_ids:
        all_ids = [b["id"] for b in bill_options]
        default_idx = all_ids.index(or_ids[0])

# Pre-compute company options (needed in both tabs)
hq_states = sorted(set(b.get("state", "") for b in all_bills if b.get("state")))


# —— Tabs —————————————————————————————————————————————————————
bill_tab, company_tab = st.tabs(["Bill View", "Company View"])


# ═══════════════════════════════════════════════════════════════
# BILL VIEW
# ═══════════════════════════════════════════════════════════════
with bill_tab:
    selected_bill_id = st.selectbox(
        "Select Bill",
        options=[b["id"] for b in bill_options],
        format_func=lambda x: bill_labels.get(x, str(x)),
        index=default_idx,
        key="selected_bill_id",
    )

    if not selected_bill_id:
        st.info("Select a bill above.")
        st.stop()

    bill_meta = bill_by_id.get(selected_bill_id)
    exposure = fetch_bill_exposure(selected_bill_id, limit=50)

    # Bill metadata header
    if bill_meta:
        title = bill_meta.get("title") or ""
        st.markdown(
            f"### {bill_meta.get('state', '')} {bill_meta.get('bill_number', '')} — {title}"
        )
        status_raw = bill_meta.get("status") or "—"
        status_label = status_raw.replace("_", " ").title()
        mats = bill_meta.get("material_categories") or []
        mat_str = ", ".join(m.replace("_", " ").title() for m in mats) if mats else "—"
        st.markdown(f"**Status:** `{status_label}` &nbsp;|&nbsp; **Materials:** {mat_str}")

    st.markdown("---")

    if not exposure:
        st.info("No company impact scores calculated for this bill yet. Run the scoring pipeline to populate results.")
    else:
        # Show fee basis disclaimer once for the bill (same fee source applies to all companies)
        first_fee_basis = (exposure[0]["impact_score"].get("score_breakdown") or {}).get("fee_basis") if exposure else None
        if first_fee_basis in _PENDING_FEE_BASES:
            st.caption("Fee Structure Pending — rates not yet published. Cost estimates use industry benchmark averages.")

        # Aggregate metrics
        total_companies = len(exposure)
        costs = [r["impact_score"].get("estimated_annual_cost") or 0 for r in exposure]
        total_cost = sum(costs)
        scores_list = [r["impact_score"].get("composite_score") for r in exposure if r["impact_score"].get("composite_score") is not None]
        avg_score = sum(scores_list) / len(scores_list) if scores_list else None

        col1, col2, col3 = st.columns(3)
        col1.metric("Companies Exposed", total_companies)
        col2.metric("Est. Total Industry Cost", format_cost(total_cost))
        col3.metric("Avg Composite Score", f"{avg_score:.0f}" if avg_score is not None else "—")

        # Peer comparison (if a company was selected in the Company tab)
        _peer_company_id = st.session_state.get("selected_company_id")
        if _peer_company_id:
            company_ids_in_ranking = [r["company"]["id"] for r in exposure]
            if _peer_company_id in company_ids_in_ranking:
                rank = company_ids_in_ranking.index(_peer_company_id) + 1
                _peer_name = next(
                    (r["company"].get("name", "Your company") for r in exposure if r["company"]["id"] == _peer_company_id),
                    "Your company",
                )
                st.markdown(
                    f"**{_peer_name}** ranks **#{rank}** of {total_companies} companies for this bill."
                )

        # Bar chart: top 20 by estimated_annual_cost
        chart_data = [
            {
                "Company": (r["company"].get("name") or "")[:35],
                "Est. Annual Cost ($)": r["impact_score"].get("estimated_annual_cost") or 0,
                "Composite Score": r["impact_score"].get("composite_score") or 0,
            }
            for r in exposure
            if (r["impact_score"].get("estimated_annual_cost") or 0) > 0
        ]
        chart_data.sort(key=lambda x: x["Est. Annual Cost ($)"], reverse=True)
        chart_data = chart_data[:20]

        if chart_data:
            st.markdown('<div class="section-header">Top Companies by Estimated Annual Cost</div>', unsafe_allow_html=True)
            try:
                import plotly.express as px

                df_chart = pd.DataFrame(chart_data)

                def score_color(s):
                    if s <= 33:
                        return "#6ee7b7"
                    elif s <= 66:
                        return "#fbbf24"
                    return "#fca5a5"

                df_chart["Color"] = df_chart["Composite Score"].apply(score_color)
                df_chart = df_chart.sort_values("Est. Annual Cost ($)")  # ascending for horizontal bar

                fig = px.bar(
                    df_chart,
                    x="Est. Annual Cost ($)",
                    y="Company",
                    orientation="h",
                    color="Color",
                    color_discrete_map="identity",
                    hover_data={"Composite Score": True, "Color": False},
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#d1d5db",
                    showlegend=False,
                    margin={"l": 10, "r": 10, "t": 10, "b": 10},
                    height=max(300, len(chart_data) * 28),
                    xaxis=dict(
                        gridcolor="#1f2937",
                        tickformat="$,.0f",
                    ),
                    yaxis=dict(gridcolor="#1f2937"),
                )
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.dataframe(
                    pd.DataFrame(chart_data)[["Company", "Est. Annual Cost ($)", "Composite Score"]],
                    use_container_width=True,
                )

        # Full ranked table
        st.markdown('<div class="section-header">Full Exposure Ranking</div>', unsafe_allow_html=True)

        rows = []
        for i, r in enumerate(exposure, 1):
            co = r["company"]
            imp = r["impact_score"]
            rows.append({
                "#": i,
                "Company": co.get("name") or "—",
                "HQ": co.get("hq_state") or "—",
                "Score": imp.get("composite_score"),
                "Est. Cost": format_cost(imp.get("estimated_annual_cost")),
                "Cost Conf.": confidence_pct(imp.get("cost_confidence")),
                "Vol. Conf.": confidence_pct(imp.get("volume_confidence")),
            })

        # Render as HTML table with score badges
        table_html = """
        <table style="width:100%; border-collapse:collapse; font-size:0.87rem; color:#d1d5db;">
          <thead>
            <tr style="border-bottom:1px solid #374151; color:#9ca3af; text-align:left;">
              <th style="padding:6px 8px;">#</th>
              <th style="padding:6px 8px;">Company</th>
              <th style="padding:6px 8px;">HQ</th>
              <th style="padding:6px 8px;">Score</th>
              <th style="padding:6px 8px;">Est. Cost</th>
              <th style="padding:6px 8px;">Cost Conf.</th>
              <th style="padding:6px 8px;">Vol. Conf.</th>
            </tr>
          </thead>
          <tbody>
        """
        for row in rows:
            table_html += f"""
            <tr style="border-bottom:1px solid #1f2937;">
              <td style="padding:6px 8px; color:#6b7280;">{row['#']}</td>
              <td style="padding:6px 8px; font-weight:500;">{row['Company']}</td>
              <td style="padding:6px 8px; color:#9ca3af;">{row['HQ']}</td>
              <td style="padding:6px 8px;">{score_badge_html(row['Score'])}</td>
              <td style="padding:6px 8px; color:#6ee7b7; font-weight:600;">{row['Est. Cost']}</td>
              <td style="padding:6px 8px; color:#9ca3af;">{row['Cost Conf.']}</td>
              <td style="padding:6px 8px; color:#9ca3af;">{row['Vol. Conf.']}</td>
            </tr>
            """
        table_html += "</tbody></table>"
        st.markdown(table_html.strip(), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# COMPANY VIEW
# ═══════════════════════════════════════════════════════════════
with company_tab:
    co_col1, co_col2 = st.columns([2, 1])
    with co_col1:
        name_search = st.text_input("Search company name", key="company_search", placeholder="e.g. Albertsons")
    with co_col2:
        hq_filter = st.selectbox("Filter by HQ state", options=["All"] + hq_states, key="company_hq_filter")

    companies = fetch_companies(hq_state=None if hq_filter == "All" else hq_filter)
    filtered_companies = companies
    if name_search:
        filtered_companies = [c for c in companies if name_search.lower() in c.get("name", "").lower()]

    company_options_ids = [""] + [c["id"] for c in filtered_companies]
    company_labels = {c["id"]: c["name"] for c in filtered_companies}

    selected_company_id = st.selectbox(
        "Select Company",
        options=company_options_ids,
        format_func=lambda x: company_labels.get(x, "— select a company —") if x else "— select a company —",
        key="selected_company_id",
    )

    if not selected_company_id:
        st.info("Select a company above to see its exposure across all bills.")
        st.stop()

    detail = fetch_company_detail(selected_company_id)
    scores = fetch_company_impact_scores(selected_company_id)

    if detail is None:
        st.error("Could not load company data. Check API connection.")
        st.stop()

    # — Company metadata card —
    naics = ", ".join(detail.get("naics_codes") or []) or "—"
    op_states = ", ".join(sorted(detail.get("operating_states") or [])) or "—"
    volume = detail.get("total_annual_volume_tonnes")
    volume_str = f"{volume:,.0f} tonnes" if volume else "—"
    vol_conf = confidence_pct(detail.get("volume_confidence"))
    hq = detail.get("hq_state") or "—"

    st.markdown(f"""
    <div class="company-card">
        <div class="co-name">{detail.get('name', '')}</div>
        <div class="co-meta">
            <span>🏠 HQ: {hq}</span>
            <span>📦 Volume: {volume_str} ({vol_conf} confidence)</span>
            <span>🏭 NAICS: {naics}</span>
        </div>
        <div class="co-meta" style="margin-top:0.4rem;">
            <span>🗺 Operating states: {op_states}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # — Material stream tags —
    materials = detail.get("materials") or []
    if materials:
        st.markdown('<div class="section-header">Material Streams</div>', unsafe_allow_html=True)
        tags_html = " ".join(
            material_tag_html(m["material_category"])
            + (f'<span style="color:#6b7280; font-size:0.75rem; margin-left:2px; margin-right:6px;">'
               f'{m["annual_volume_tonnes"]:,.0f}t</span>'
               if m.get("annual_volume_tonnes") else "")
            for m in materials
        )
        st.markdown(tags_html, unsafe_allow_html=True)

    # — State presences —
    presences = detail.get("state_presences") or []
    if presences:
        st.markdown('<div class="section-header">State Presence</div>', unsafe_allow_html=True)
        by_type: dict = defaultdict(list)
        for p in presences:
            by_type[p.get("presence_type", "other")].append(p.get("state", "?"))
        presence_parts = []
        type_order = ["manufacturing", "distribution", "headquarters", "retail", "registered_agent", "sales"]
        for ptype in type_order:
            if ptype in by_type:
                states_str = ", ".join(sorted(by_type[ptype]))
                label = ptype.replace("_", " ").title()
                presence_parts.append(f"**{label}:** {states_str}")
        st.markdown("&nbsp;&nbsp;|&nbsp;&nbsp;".join(presence_parts))

    # — Ranked bill list —
    st.markdown('<div class="section-header">Bill Exposure Ranking</div>', unsafe_allow_html=True)

    if not scores:
        st.info("No impact scores found for this company yet. Run the scoring pipeline to populate results.")
    else:
        sorted_scores = sorted(
            scores,
            key=lambda s: s.get("composite_score") or 0,
            reverse=True,
        )

        for score in sorted_scores:
            bill_id = score.get("bill_id")
            bill_info = bill_by_id.get(bill_id)
            if bill_info:
                bill_label = f"{bill_info.get('state', '')} {bill_info.get('bill_number', '')} — {(bill_info.get('title') or '')[:60]}"
            else:
                bill_label = f"Bill {bill_id}"

            s_html = score_badge_html(score.get("composite_score"))
            cost_str = format_cost(score.get("estimated_annual_cost"))
            conf_str = confidence_pct(score.get("cost_confidence"))
            fee_basis = (score.get("score_breakdown") or {}).get("fee_basis")
            badge_html = fee_basis_badge_html(fee_basis)

            st.markdown(f"""
            <div class="bill-row">
                <div class="bill-label">{s_html}&nbsp;&nbsp;{bill_label}</div>
                <div class="bill-cost">{cost_str}{badge_html}</div>
                <div class="bill-conf">{conf_str} conf.</div>
            </div>
            """, unsafe_allow_html=True)

            if fee_basis in _PENDING_FEE_BASES:
                st.caption("Fee Structure Pending — rates not yet published. Cost estimate uses industry benchmark averages.")

    # — Exposure Brief —
    st.markdown('<div class="section-header">Exposure Brief</div>', unsafe_allow_html=True)

    # Default to whatever was last selected in the Bill tab (if any)
    _bill_tab_selection = st.session_state.get("selected_bill_id")
    _brief_default_idx = 0
    if _bill_tab_selection and _bill_tab_selection in [b["id"] for b in bill_options]:
        _brief_default_idx = [b["id"] for b in bill_options].index(_bill_tab_selection)

    brief_bill_id = st.selectbox(
        "Select bill for exposure brief",
        options=[b["id"] for b in bill_options],
        format_func=lambda x: bill_labels.get(x, str(x)),
        index=_brief_default_idx,
        key="brief_bill_id",
    )

    if not brief_bill_id:
        st.caption("Select a bill above to generate an Exposure Brief for this company.")
    else:
        with st.spinner("Loading exposure brief..."):
            brief_data = fetch_exposure_brief(selected_company_id, brief_bill_id)

        if brief_data is None:
            st.info(
                "Exposure brief generation is disabled or unavailable. "
                "Set `ENABLE_INTERPRETATION=true` and ensure the Anthropic API key is configured."
            )
        elif brief_data.get("error"):
            st.warning(f"Brief generation error: {brief_data.get('error')}. Raw output available for debugging.")
        else:
            brief_json = brief_data.get("brief_json") or brief_data

            # Exposure summary
            summary = brief_json.get("exposure_summary")
            if summary:
                st.markdown(f"> {summary}")

            # Cost breakdown
            cost_bd = brief_json.get("cost_breakdown") or {}
            if cost_bd:
                st.markdown('<div class="section-header" style="font-size:0.95rem; margin-top:1rem;">Cost Breakdown</div>', unsafe_allow_html=True)
                cb_col1, cb_col2, cb_col3 = st.columns(3)
                total_cost = cost_bd.get("total_estimated_annual_cost")
                obligation = cost_bd.get("estimated_annual_obligation")
                penalty = cost_bd.get("penalty_risk_estimate")
                cb_col1.metric("Est. Annual Obligation", format_cost(obligation))
                cb_col2.metric("Penalty Risk", format_cost(penalty))
                cb_col3.metric("Total Est. Cost", format_cost(total_cost))
                if cost_bd.get("notes"):
                    st.caption(f"Assumptions: {cost_bd['notes']} | Confidence: {cost_bd.get('confidence', '—')}")

            # Peer context
            peer_ctx = brief_json.get("peer_context")
            if peer_ctx:
                st.markdown(f"**Peer Context:** {peer_ctx}")

            # Redesign opportunities
            redesign = brief_json.get("redesign_opportunities") or []
            if redesign:
                st.markdown('<div class="section-header" style="font-size:0.95rem; margin-top:1rem;">Redesign Opportunities</div>', unsafe_allow_html=True)
                for opp in redesign:
                    st.markdown(f"- {opp}")

            # CTA from brief
            cta = brief_json.get("next_step_cta")
            if cta:
                st.info(f"**Next Step:** {cta}")

    # — CTA —
    st.markdown("---")
    st.markdown("**Need a deeper analysis?**")
    st.caption("Contact your account manager to generate a full EPR redesign strategy for this company.")
    st.link_button("Request Custom Analysis \u2197", "mailto:hello@signalscout.io?subject=Custom%20EPR%20Analysis%20Request")
