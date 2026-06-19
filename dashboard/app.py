"""
SignalScout — EPR Legislative Intelligence Dashboard
Main landing page with key metrics, state map, and bill explorer.
"""
import os
from collections import Counter
from datetime import date as _date

import httpx
import pandas as pd
import streamlit as st

from styles import inject_shared_styles

st.set_page_config(
    page_title="SignalScout — EPR Legislative Intelligence",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# —— Styling ————————————————————————————————————————————————
inject_shared_styles()
st.markdown("""
<style>
    /* Hero banner */
    .hero {
        background: linear-gradient(135deg, #0f2b1d 0%, #1a4d2e 50%, #0d3320 100%);
        border-radius: 12px;
        padding: 2.5rem 2rem;
        margin-bottom: 1.5rem;
        border: 1px solid #2d6b45;
    }
    .hero h1 {
        color: #e8f5ec;
        font-size: 2.2rem;
        margin: 0 0 0.3rem 0;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .hero p {
        color: #8cc5a0;
        font-size: 1.05rem;
        margin: 0;
    }

    /* Alert banner */
    .alert-banner {
        background: linear-gradient(90deg, #78350f, #92400e);
        border: 1px solid #b45309;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.5rem;
        color: #fef3c7;
        font-size: 0.9rem;
    }
    .alert-banner strong { color: #fbbf24; }
</style>
""", unsafe_allow_html=True)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


# —— Data fetching ——————————————————————————————————————————
@st.cache_data(ttl=300)
def fetch_bills():
    try:
        resp = httpx.get(
            f"{API_BASE}/bills",
            params={"ce_relevant": True, "limit": 500},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def fetch_deadlines():
    try:
        resp = httpx.get(
            f"{API_BASE}/bills/deadlines/upcoming",
            params={"days_ahead": 365},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def fetch_federal():
    try:
        resp = httpx.get(
            f"{API_BASE}/federal-actions",
            params={"limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# —— Helpers ————————————————————————————————————————————————

def normalize_status(status: str | None) -> str:
    if status == "enacted":
        return "Enacted"
    if status in ("introduced", "in_committee", "passed_chamber"):
        return "Pending"
    if status in ("failed", "vetoed", "withdrawn"):
        return status.title()
    return "Under Review" if status else "\u2014"


def urgency_indicator(urgency: str) -> str:
    if urgency == "high":
        return "🔴 High"
    elif urgency == "medium":
        return "🟡 Medium"
    return "⚪ Low"


# —— Sidebar ————————————————————————————————————————————————
with st.sidebar:
    st.markdown("### 🔭 SignalScout")
    st.caption("EPR Legislative Intelligence")
    st.markdown("---")
    st.markdown(
        "Track US state-level EPR legislation, right-to-repair, "
        "recycled content mandates, deposit return schemes, and "
        "federal preemption actions across **all major material categories**."
    )
    st.markdown("---")
    st.caption("Map filters (state, instrument type, enacted only) are directly above the map.")
    st.markdown("---")
    st.markdown(
        "<div style='color:#6b7280;font-size:0.75rem;'>"
        "Data: LegiScan · Open States · Federal Register<br>"
        "Classification: Claude Haiku + Sonnet pipeline"
        "</div>",
        unsafe_allow_html=True,
    )


# —— Hero —————————————————————————————————————————————————
st.markdown("""
<div class="hero">
    <h1>SignalScout Dashboard</h1>
    <p>US EPR legislative intelligence — monitoring all 50 states + DC across 10+ material categories</p>
</div>
""", unsafe_allow_html=True)


# —— Fetch data ——————————————————————————————————————————————
bills = fetch_bills()
deadlines = fetch_deadlines()
federal = fetch_federal()

# Compute metrics
if bills:
    enacted_count = len([b for b in bills if b.get("status") == "enacted"])
    states_with_activity = len(set(b.get("state", "") for b in bills))

    all_cats = set()
    for b in bills:
        for cat in (b.get("material_categories") or []):
            all_cats.add(cat)
    material_count = len(all_cats)

    packaging_states = set()
    pkg_cats = {"plastic_packaging", "paper_packaging"}
    for b in bills:
        if b.get("status") == "enacted":
            cats = set(b.get("material_categories") or [])
            if cats & pkg_cats:
                packaging_states.add(b.get("state"))
    packaging_state_count = len(packaging_states)
else:
    enacted_count = states_with_activity = material_count = packaging_state_count = 0

deadline_count = len(deadlines) if deadlines else 0
federal_count = len(federal) if federal else 0
high_preemption = len([f for f in (federal or []) if f.get("preemption_risk") == "High"])


# —— Metrics ————————————————————————————————————————————————
m1, m2, m3, m4 = st.columns(4)
m1.metric("Enacted EPR Laws", enacted_count, f"{packaging_state_count} packaging EPR states")
m2.metric("States With Activity", states_with_activity, "across all instrument types")
m3.metric("Material Categories", material_count, "packaging · e-waste · batteries · more")
m4.metric("Upcoming Deadlines", deadline_count, "within next 365 days")


# —— Federal Preemption Alert ———————————————————————————————
if high_preemption > 0:
    st.markdown(f"""
    <div class="alert-banner">
        <strong>⚠ Federal Preemption Watch:</strong> {high_preemption} high-risk federal action(s) tracked.
        The Oregon NAW constitutional challenge (trial July 13, 2026) could set precedent for
        Dormant Commerce Clause attacks on all state packaging EPR programs.
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="alert-banner">
        <strong>⚠ Federal Preemption Watch:</strong>
        The Oregon NAW case (trial July 13, 2026) could set precedent for
        Dormant Commerce Clause attacks on all state packaging EPR programs.
        Monitor the Federal Actions page for updates.
    </div>
    """, unsafe_allow_html=True)


# —— State Explorer ————————————————————————————————————————
st.markdown('<div class="section-header">State Explorer</div>', unsafe_allow_html=True)

if not bills:
    st.warning("No bill data available. Ensure the API is running and the database is seeded.")
else:
    # Filter controls above the map
    all_states_sorted = sorted(
        set(b.get("state", "") for b in bills if b.get("state") in STATE_NAMES)
    )
    state_options = ["All States"] + [f"{s} — {STATE_NAMES[s]}" for s in all_states_sorted]

    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 1])
    with ctrl_col1:
        state_select = st.selectbox(
            "State",
            options=state_options,
            index=0,
            key="state_selector",
        )
    with ctrl_col2:
        instrument_select = st.selectbox(
            "Instrument type",
            options=["All Types", "epr", "right_to_repair", "recycled_content", "deposit_return", "labeling"],
            format_func=lambda x: x if x == "All Types" else x.replace("_", " ").title(),
        )
    with ctrl_col3:
        enacted_only = st.checkbox("Enacted only", value=False)

    # Parse selected state abbreviation
    selected_state = None
    if state_select != "All States":
        selected_state = state_select.split(" — ")[0]

    # Build map data (always show all states for map context)
    map_bills = [b for b in bills if b.get("status") == "enacted"] if enacted_only else bills
    if instrument_select != "All Types":
        map_bills = [b for b in map_bills if b.get("instrument_type") == instrument_select]

    state_counts = Counter(b.get("state", "") for b in map_bills)
    state_df = pd.DataFrame([
        {
            "State": abbr,
            "State Name": STATE_NAMES.get(abbr, abbr),
            "Laws": count,
        }
        for abbr, count in state_counts.items()
        if abbr in STATE_NAMES
    ])

    # —— Choropleth ——————————————————————————————————————————
    try:
        import plotly.express as px

        if not state_df.empty:
            # Highlight selected state
            state_df["Selected"] = state_df["State"].apply(
                lambda s: 1.5 if s == selected_state else 1.0
            )

            fig = px.choropleth(
                state_df,
                locations="State",
                locationmode="USA-states",
                color="Laws",
                scope="usa",
                color_continuous_scale=[
                    [0.0, "#1f2937"],
                    [0.25, "#14532d"],
                    [0.5, "#166534"],
                    [0.75, "#22c55e"],
                    [1.0, "#86efac"],
                ],
                hover_name="State Name",
                hover_data={"Laws": True, "State": False, "Selected": False},
                labels={"Laws": "Bills"},
            )
            # Add a marker for the selected state
            if selected_state and selected_state in STATE_NAMES:
                sel_row = state_df[state_df["State"] == selected_state]
                if not sel_row.empty:
                    fig.add_choropleth(
                        locations=[selected_state],
                        locationmode="USA-states",
                        z=[sel_row.iloc[0]["Laws"]],
                        colorscale=[[0, "#facc15"], [1, "#facc15"]],
                        showscale=False,
                        hoverinfo="skip",
                        marker_line_color="#facc15",
                        marker_line_width=3,
                    )

            fig.update_layout(
                geo=dict(
                    bgcolor="rgba(0,0,0,0)",
                    lakecolor="rgba(0,0,0,0)",
                    landcolor="#1f2937",
                    showlakes=False,
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                height=420,
                coloraxis_colorbar=dict(
                    title="Bills",
                    titlefont=dict(color="#9ca3af"),
                    tickfont=dict(color="#9ca3af"),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data matches the current filters.")
    except ImportError:
        st.warning("Install plotly for the choropleth map: `pip install plotly`")
        st.dataframe(state_df, use_container_width=True, hide_index=True)

    # —— Bill Table (filtered by state selection) ————————————
    label = f"Bills — {selected_state} ({STATE_NAMES.get(selected_state, '')})" if selected_state else "Bills — All States"
    st.markdown(f'<div class="section-header">{label}</div>', unsafe_allow_html=True)

    table_bills = [b for b in bills if b.get("ce_relevant")]
    if selected_state:
        table_bills = [b for b in table_bills if b.get("state") == selected_state]
    if enacted_only:
        table_bills = [b for b in table_bills if b.get("status") == "enacted"]
    if instrument_select != "All Types":
        table_bills = [b for b in table_bills if b.get("instrument_type") == instrument_select]

    table_bills.sort(key=lambda b: b.get("last_action_date") or "", reverse=True)

    if table_bills:
        table_data = []
        for b in table_bills:
            cats = b.get("material_categories") or []
            cat_str = ", ".join(c.replace("_", " ").title() for c in cats[:3])
            if len(cats) > 3:
                cat_str += f" +{len(cats) - 3}"
            table_data.append({
                "State": b.get("state", ""),
                "Bill": b.get("bill_number", "\u2014"),
                "Title": b.get("title") or "Untitled"[:80],
                "Status": normalize_status(b.get("status")),
                "Urgency": urgency_indicator(b.get("urgency") or "low"),
                "Materials": cat_str,
                "Type": (b.get("instrument_type") or "\u2014").replace("_", " ").title(),
                "Last Action": b.get("last_action_date") or "\u2014",
                "Source": b.get("source_url") or "",
            })

        df = pd.DataFrame(table_data)
        st.caption(f"{len(df)} bill(s) — click a row to see details")

        selection = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(len(df) * 38 + 40, 500),
            selection_mode="single-row",
            on_select="rerun",
            column_config={
                "Source": st.column_config.LinkColumn("Source", display_text="View \u2197"),
            },
        )

        selected_rows = selection.selection.get("rows", [])
        selected_idx = selected_rows[0] if selected_rows else None

        if selected_idx is not None and selected_idx < len(table_bills):
            b = table_bills[selected_idx]
            st.divider()
            st.markdown('<div class="section-header">Selected Bill Details</div>', unsafe_allow_html=True)
            cd = b.get("compliance_details") or {}
            today_str = _date.today().isoformat()
            title = b.get("title") or "Untitled"
            st.markdown(f"### {b.get('state', '?')} {b.get('bill_number', '?')} — {title}")

            if b.get("ai_summary"):
                st.info(b["ai_summary"])

            if cd:
                col_a, col_b = st.columns(2)
                with col_a:
                    if cd.get("producer_definition"):
                        st.markdown("**Who's covered**")
                        st.markdown(cd["producer_definition"])
                    if cd.get("covered_products"):
                        st.markdown("**Covered products**")
                        for p in cd["covered_products"][:3]:
                            st.markdown(f"- {p}")
                    if cd.get("exemptions"):
                        st.markdown("**Exemptions**")
                        for e in cd["exemptions"][:3]:
                            st.markdown(f"- {e}")
                    bill_deadlines = cd.get("deadlines") or []
                    if bill_deadlines:
                        future = [d for d in bill_deadlines if (d.get("date") or "") >= today_str]
                        next_dl = future[0] if future else bill_deadlines[0]
                        dl_label = {"registration": "Registration", "fee_payment": "Fee payment",
                                    "compliance": "Compliance", "reporting": "Reporting"}.get(
                            next_dl.get("type", ""), next_dl.get("type", "").title())
                        st.markdown("**Next deadline**")
                        st.markdown(f"`{next_dl.get('date', '?')}` — {dl_label}: {next_dl.get('description', '')}")
                with col_b:
                    if cd.get("fees"):
                        fees = cd["fees"]
                        structure = fees.get("structure", "").replace("_", " ").title()
                        st.markdown(f"**Fee structure** — `{structure}`")
                        if fees.get("details"):
                            st.markdown(fees["details"])
                    if cd.get("producer_obligations"):
                        st.markdown("**Producer obligations**")
                        for o in cd["producer_obligations"][:4]:
                            st.markdown(f"- {o}")
                    if cd.get("pro_requirements"):
                        st.markdown("**PRO / stewardship org**")
                        st.markdown(cd["pro_requirements"])
                    if cd.get("enforcement"):
                        enf = cd["enforcement"]
                        st.markdown(f"**Enforcement** — {enf.get('agency', '—')}")
                        if enf.get("penalties"):
                            st.markdown(f"Penalties: {enf['penalties']}")
                if cd.get("preemption_risk"):
                    risk = cd["preemption_risk"]
                    risk_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(risk, "⚪")
                    notes = cd.get("preemption_notes", "")
                    if risk == "High" and notes:
                        st.warning(f"{risk_icon} **Preemption risk: {risk}** — {notes}")
                    elif risk != "Low":
                        st.markdown(f"{risk_icon} **Preemption risk: {risk}**")
            else:
                cats = b.get("material_categories") or []
                col_a, col_b = st.columns(2)
                with col_a:
                    if cats:
                        st.markdown(f"**Materials:** {', '.join(c.replace('_', ' ').title() for c in cats)}")
                    st.markdown(f"**Instrument:** {(b.get('instrument_type') or '—').replace('_', ' ').title()}")
                with col_b:
                    st.markdown(f"**Last action:** {b.get('last_action_date') or '—'}")

            if b.get("source_url"):
                st.markdown(f"[View official source ↗]({b['source_url']})")
    else:
        st.info("No bills match the current filters.")


# —— Material Category Breakdown ————————————————————————————
st.markdown('<div class="section-header">Coverage by Material Category</div>', unsafe_allow_html=True)

if bills:
    cat_counts = Counter()
    for b in bills:
        if b.get("status") == "enacted":
            for cat in (b.get("material_categories") or []):
                cat_counts[cat] += 1

    if cat_counts:
        cat_df = pd.DataFrame(
            sorted(cat_counts.items(), key=lambda x: -x[1]),
            columns=["Category", "Enacted Laws"],
        )
        cat_df["Category"] = cat_df["Category"].str.replace("_", " ").str.title()
        st.bar_chart(cat_df.set_index("Category"), height=280)
    else:
        st.info("No enacted bills with material categories found.")


# —— Quick Navigation ———————————————————————————————————————
st.markdown('<div class="section-header">Quick Navigation</div>', unsafe_allow_html=True)
nav_col1, nav_col2, nav_col3 = st.columns(3)
with nav_col1:
    st.page_link("pages/02_bill_tracker.py", label="📋 Bill Tracker", help="Filter and search all tracked legislation")
with nav_col2:
    st.page_link("pages/03_compliance_cal.py", label="📅 Compliance Calendar", help="Upcoming deadlines and registration dates")
with nav_col3:
    st.page_link("pages/04_federal.py", label="🏛️ Federal Actions", help="Federal preemption risk and regulatory actions")
