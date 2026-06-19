"""
SignalScout — Compliance Deadline Calendar
Upcoming compliance, registration, and fee payment deadlines.
"""
import os
from datetime import date, timedelta

import httpx
import pandas as pd
import streamlit as st

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from styles import inject_shared_styles

st.set_page_config(page_title="SignalScout — Compliance Calendar", page_icon="🔭", layout="wide")

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

inject_shared_styles()
st.markdown("""
<style>
.deadline-card {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}
.deadline-card .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.5rem;
}
.deadline-card .state-bill {
    color: #f9fafb;
    font-weight: 600;
    font-size: 1rem;
}
.deadline-card .days-until {
    color: #6ee7b7;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;
}
.deadline-card .days-until.urgent { color: #ef4444; }
.deadline-card .days-until.soon { color: #f59e0b; }
.deadline-card .type-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-right: 0.5rem;
}
.type-registration { background: #1e3a5f; color: #93c5fd; }
.type-fee_payment { background: #422006; color: #fbbf24; }
.type-compliance { background: #1a2e05; color: #86efac; }
.type-reporting { background: #2d1b4e; color: #c4b5fd; }
.deadline-card .desc { color: #9ca3af; font-size: 0.925rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def fetch_deadlines(days_ahead: int, state: str | None):
    params = {"days_ahead": days_ahead}
    if state and state != "All":
        params["state"] = state
    try:
        resp = httpx.get(f"{API_BASE}/bills/deadlines/upcoming", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch deadlines: {e}")
        return []


@st.cache_data(ttl=300)
def fetch_all_bills():
    """Fetch bills to get compliance_details with deadlines that may not be in the deadlines table yet."""
    try:
        resp = httpx.get(
            f"{API_BASE}/bills",
            params={"ce_relevant": True, "limit": 500},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


# —— Sidebar ————————————————————————————————————————————————
with st.sidebar:
    st.markdown("### Filters")
    horizon = st.selectbox("Time Horizon", [30, 90, 180, 365, 730], index=3, format_func=lambda x: f"{x} days")
    state_filter = st.selectbox("State", ["All", "CA", "CO", "CT", "DC", "IL", "MA", "MD", "ME", "MI", "MN", "NJ", "NY", "OR", "RI", "VT", "WA"])
    show_past = st.checkbox("Include past deadlines (reference)", value=False)


st.title("📅 Compliance Deadline Calendar")
st.caption("Upcoming compliance, registration, reporting, and fee payment deadlines.")

# —— Fetch data —————————————————————————————————————————————
deadlines = fetch_deadlines(horizon, state_filter if state_filter != "All" else None)
bills = fetch_all_bills()

# Also extract deadlines from compliance_details for bills that may have them
# (in case the deadlines table is incomplete)
today = date.today()
cutoff = today + timedelta(days=horizon)

extra_deadlines = []
for b in bills:
    cd = b.get("compliance_details")
    if not cd or not isinstance(cd, dict):
        continue
    for dl in cd.get("deadlines", []):
        dl_date_str = dl.get("date")
        if not dl_date_str:
            continue
        try:
            dl_date = date.fromisoformat(dl_date_str[:10])
        except ValueError:
            continue

        if show_past or (today <= dl_date <= cutoff):
            if state_filter != "All" and b.get("state") != state_filter:
                continue
            extra_deadlines.append({
                "id": None,
                "state": b.get("state", "?"),
                "deadline_type": dl.get("type", "compliance"),
                "deadline_date": dl_date_str[:10],
                "description": dl.get("description", ""),
                "who_affected": dl.get("who_affected"),
                "bill_id": b.get("id"),
                "bill_number": b.get("bill_number"),
                "bill_title": b.get("title"),
            })

# Merge and deduplicate
seen_keys = set()
all_deadlines = []
for dl in deadlines:
    key = (dl.get("state"), dl.get("deadline_date"), dl.get("deadline_type"))
    if key not in seen_keys:
        seen_keys.add(key)
        all_deadlines.append(dl)

for dl in extra_deadlines:
    key = (dl.get("state"), dl.get("deadline_date"), dl.get("deadline_type"))
    if key not in seen_keys:
        seen_keys.add(key)
        all_deadlines.append(dl)

# Filter past if needed
if not show_past:
    all_deadlines = [dl for dl in all_deadlines if dl.get("deadline_date", "") >= today.isoformat()]

# Sort by date
all_deadlines.sort(key=lambda d: d.get("deadline_date", "9999"))


# —— Summary metrics ————————————————————————————————————————
thirty_day_cutoff = (today + timedelta(days=30)).isoformat()
ninety_day_cutoff = (today + timedelta(days=90)).isoformat()

within_30 = [dl for dl in all_deadlines if dl.get("deadline_date", "") <= thirty_day_cutoff]
within_90 = [dl for dl in all_deadlines if dl.get("deadline_date", "") <= ninety_day_cutoff]

next_deadline_date = all_deadlines[0].get("deadline_date", "—") if all_deadlines else "None upcoming"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Upcoming", len(all_deadlines))
col2.metric("Within 30 Days", len(within_30))
col3.metric("Within 90 Days", len(within_90))
col4.metric("Next Deadline", next_deadline_date)

if within_30:
    st.error(f"⚠️ **{len(within_30)} deadline(s) within 30 days!** Review immediately.")


# —— Timeline visualization —————————————————————————————————
if all_deadlines:
    st.markdown('<div class="section-header">Deadline Timeline</div>', unsafe_allow_html=True)

    try:
        import plotly.express as px

        timeline_data = []
        for dl in all_deadlines:
            dl_date = dl.get("deadline_date", "")
            label = f"{dl.get('state', '?')} {dl.get('bill_number', '?')}"
            timeline_data.append({
                "Label": label,
                "Date": dl_date,
                "Type": (dl.get("deadline_type") or "compliance").replace("_", " ").title(),
                "State": dl.get("state", "?"),
                "Description": dl.get("description", ""),
                "Days Until": (date.fromisoformat(dl_date[:10]) - today).days if dl_date else 0,
            })

        tl_df = pd.DataFrame(timeline_data)
        tl_df["Date"] = pd.to_datetime(tl_df["Date"])

        fig = px.scatter(
            tl_df,
            x="Date",
            y="Label",
            color="Type",
            size_max=12,
            hover_data=["State", "Description", "Days Until", "Type"],
            color_discrete_map={
                "Registration": "#3b82f6",
                "Fee Payment": "#f59e0b",
                "Compliance": "#22c55e",
                "Reporting": "#8b5cf6",
                "Other": "#6b7280",
            },
        )
        fig.update_traces(marker=dict(size=14))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=max(200, len(timeline_data) * 50),
            margin=dict(l=0, r=0, t=10, b=30),
            xaxis=dict(gridcolor="#1f2937", title="", tickfont=dict(color="#9ca3af")),
            yaxis=dict(gridcolor="#1f2937", title="", tickfont=dict(color="#9ca3af", size=10)),
            legend=dict(font=dict(color="#9ca3af")),
            showlegend=True,
        )
        # Add "today" vertical line
        fig.add_vline(x=today.isoformat(), line_dash="dash", line_color="#ef4444", opacity=0.5)
        fig.add_annotation(x=today.isoformat(), y=1.05, yref="paper", text="Today", showarrow=False, font=dict(color="#ef4444", size=10))

        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Install plotly for the timeline chart: `pip install plotly`")


# —— Deadline cards —————————————————————————————————————————
st.markdown('<div class="section-header">Deadline Details</div>', unsafe_allow_html=True)

for dl in all_deadlines:
    dl_date_str = dl.get("deadline_date", "")
    try:
        dl_date = date.fromisoformat(dl_date_str[:10])
        days_until = (dl_date - today).days
    except (ValueError, TypeError):
        days_until = None

    state = dl.get("state", "?")
    bill_num = dl.get("bill_number") or "—"
    bill_title = dl.get("bill_title") or ""
    dl_type = dl.get("deadline_type", "compliance")
    desc = dl.get("description", "No description")

    # Days until styling
    if days_until is not None:
        if days_until <= 0:
            days_class = "urgent"
            days_text = f"⚠️ {'OVERDUE' if days_until < 0 else 'TODAY'}"
        elif days_until <= 30:
            days_class = "urgent"
            days_text = f"{days_until} days"
        elif days_until <= 90:
            days_class = "soon"
            days_text = f"{days_until} days"
        else:
            days_class = ""
            days_text = f"{days_until} days"
    else:
        days_class = ""
        days_text = "—"

    type_class = f"type-{dl_type}" if dl_type in ["registration", "fee_payment", "compliance", "reporting"] else "type-compliance"

    st.markdown(f"""
    <div class="deadline-card">
        <div class="header">
            <span class="state-bill">{state} {bill_num} — {dl_date_str}</span>
            <span class="days-until {days_class}">{days_text}</span>
        </div>
        <span class="type-badge {type_class}">{dl_type.replace('_', ' ').title()}</span>
        <div class="desc">{desc}</div>
    </div>
    """, unsafe_allow_html=True)


# —— Reference table ————————————————————————————————————————
if all_deadlines:
    st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)

    export_data = []
    for dl in all_deadlines:
        try:
            dl_date = date.fromisoformat(dl.get("deadline_date", "")[:10])
            days = (dl_date - today).days
        except (ValueError, TypeError):
            days = None
        export_data.append({
            "State": dl.get("state", ""),
            "Bill": dl.get("bill_number", ""),
            "Date": dl.get("deadline_date", ""),
            "Type": (dl.get("deadline_type") or "").replace("_", " ").title(),
            "Description": dl.get("description", ""),
            "Days Until": days,
        })

    export_df = pd.DataFrame(export_data)
    csv = export_df.to_csv(index=False)
    st.download_button("📥 Download Deadlines CSV", csv, "signalscout_deadlines.csv", "text/csv")
else:
    st.info(
        "No upcoming deadlines found within the selected time horizon. "
        "Try extending the horizon or checking if the database has been seeded with compliance deadlines."
    )
