"""
SignalScout — Bill Tracker
Searchable, filterable table of all tracked legislation with detail expansion.
"""
import os
from datetime import date as _date

import httpx
import pandas as pd
import streamlit as st

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from styles import inject_shared_styles

st.set_page_config(page_title="SignalScout — Bill Tracker", page_icon="🔭", layout="wide")

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

inject_shared_styles()
st.markdown("""
<style>
.urgency-high { color: #ef4444; font-weight: 600; }
.urgency-medium { color: #f59e0b; font-weight: 600; }
.urgency-low { color: #6b7280; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def fetch_all_bills():
    try:
        resp = httpx.get(
            f"{API_BASE}/bills",
            params={"limit": 500},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch bills: {e}")
        return []



def urgency_indicator(urgency: str) -> str:
    if urgency == "high":
        return "🔴 High"
    elif urgency == "medium":
        return "🟡 Medium"
    return "⚪ Low"


bills = fetch_all_bills()

st.title("📋 EPR Bill Tracker")

if not bills:
    st.warning("No bills loaded. Check API connection and database.")
    st.stop()

# —— Sidebar filters ————————————————————————————————————————
all_states = sorted(set(b.get("state", "") for b in bills))
all_statuses = sorted(set(b.get("status", "") for b in bills if b.get("status")))
all_instruments = sorted(set(b.get("instrument_type", "") for b in bills if b.get("instrument_type")))
all_cats = sorted(set(
    cat for b in bills for cat in (b.get("material_categories") or [])
))

with st.sidebar:
    st.markdown("### Filters")
    st.markdown("*Only showing bills relevant for EPR, repair, deposit return, eco-modulation fees, subsidies, and procurement policies that support a circular economy.*")

    search_text = st.text_input("🔍 Search bills", placeholder="e.g. packaging, SB 54, repair...")

    filter_state = st.multiselect("State", options=all_states, default=[])
    filter_status = st.multiselect("Status", options=all_statuses, default=[])
    filter_instrument = st.multiselect("Instrument Type", options=all_instruments, default=[])
    filter_material = st.multiselect(
        "Material Category",
        options=all_cats,
        format_func=lambda x: x.replace("_", " ").title(),
        default=[],
    )

    sort_by = st.selectbox("Sort by", ["Last Action Date", "State", "Bill Number"])

# —— Apply filters (EPR-only always on) ————————————————————
filtered = [b for b in bills if b.get("ce_relevant")]

if filter_state:
    filtered = [b for b in filtered if b.get("state") in filter_state]
if filter_status:
    filtered = [b for b in filtered if b.get("status") in filter_status]
if filter_instrument:
    filtered = [b for b in filtered if b.get("instrument_type") in filter_instrument]
if filter_material:
    filtered = [
        b for b in filtered
        if any(c in (b.get("material_categories") or []) for c in filter_material)
    ]
if search_text:
    q = search_text.lower()
    filtered = [
        b for b in filtered
        if q in (b.get("title") or "").lower()
        or q in (b.get("bill_number") or "").lower()
        or q in (b.get("description") or "").lower()
        or q in (b.get("ai_summary") or "").lower()
        or q in (b.get("state") or "").lower()
    ]

# Sort
sort_map = {
    "Last Action Date": lambda b: b.get("last_action_date") or "",
    "State": lambda b: b.get("state") or "",
    "Bill Number": lambda b: b.get("bill_number") or "",
}
filtered.sort(key=sort_map.get(sort_by, sort_map["Last Action Date"]), reverse=(sort_by == "Last Action Date"))

# —— Summary metrics ————————————————————————————————————————
st.caption(f"Showing {len(filtered)} of {len(bills)} bills")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Matching Bills", len(filtered))
col2.metric("Enacted", len([b for b in filtered if b.get("status") == "enacted"]))
col3.metric("High Urgency", len([b for b in filtered if b.get("urgency") == "high"]))
col4.metric("States", len(set(b.get("state", "") for b in filtered)))

# —— Table ——————————————————————————————————————————————————
def normalize_status(status: str | None) -> str:
    if status == "enacted":
        return "Enacted"
    if status in ("introduced", "in_committee", "passed_chamber"):
        return "Pending"
    if status in ("failed", "vetoed", "withdrawn"):
        return status.title()
    return "Under Review" if status else "\u2014"


if filtered:
    table_data = []
    for b in filtered:
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

    # —— Table (rendered first to capture selection) ————————
    st.markdown('<div class="section-header">Matching Bills</div>', unsafe_allow_html=True)
    selection = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(len(df) * 38 + 40, 600),
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "Source": st.column_config.LinkColumn("Source", display_text="View \u2197"),
        },
    )

    st.caption(f"{len(df)} bill(s) — click a row to see details below")
    csv = df.to_csv(index=False)
    st.download_button("\U0001f4e5 Download CSV", csv, "signalscout_bills.csv", "text/csv")

    selected_rows = selection.selection.get("rows", [])
    selected_idx = selected_rows[0] if selected_rows else None

    # —— Detail panel — below table, requires explicit row selection ——
    st.divider()
    st.markdown('<div class="section-header">Selected Bill Details</div>', unsafe_allow_html=True)

    if selected_idx is None:
        st.info("Click a row in the table above to see bill details.")
    else:
        b = filtered[selected_idx] if selected_idx < len(filtered) else None

    if selected_idx is not None and b is not None:
        cd = b.get("compliance_details") or {}
        today_str = _date.today().isoformat()

        bill_num = b.get("bill_number") or "?"
        state = b.get("state", "?")
        title = b.get("title") or "Untitled"
        status = b.get("status", "unknown")

        st.markdown(f"### {state} {bill_num} \u2014 {title}")

        if b.get("ai_summary"):
            st.info(b["ai_summary"])

        if cd:
            col_a, col_b = st.columns(2)

            with col_a:
                if cd.get("producer_definition"):
                    st.markdown("**Who\u2019s covered**")
                    st.markdown(cd["producer_definition"])

                if cd.get("covered_products"):
                    st.markdown("**Covered products**")
                    for p in cd["covered_products"][:3]:
                        st.markdown(f"- {p}")

                if cd.get("exemptions"):
                    st.markdown("**Exemptions**")
                    for e in cd["exemptions"][:3]:
                        st.markdown(f"- {e}")

                deadlines = cd.get("deadlines") or []
                if deadlines:
                    future = [d for d in deadlines if (d.get("date") or "") >= today_str]
                    next_dl = future[0] if future else deadlines[0]
                    dl_label = {"registration": "Registration", "fee_payment": "Fee payment",
                                "compliance": "Compliance", "reporting": "Reporting"}.get(
                        next_dl.get("type", ""), next_dl.get("type", "").title())
                    st.markdown("**Next deadline**")
                    st.markdown(f"`{next_dl.get('date', '?')}` \u2014 {dl_label}: {next_dl.get('description', '')}")

            with col_b:
                if cd.get("fees"):
                    fees = cd["fees"]
                    structure = fees.get("structure", "").replace("_", " ").title()
                    st.markdown(f"**Fee structure** \u2014 `{structure}`")
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
                    st.markdown(f"**Enforcement** \u2014 {enf.get('agency', '\u2014')}")
                    if enf.get("penalties"):
                        st.markdown(f"Penalties: {enf['penalties']}")

            if cd.get("preemption_risk"):
                risk = cd["preemption_risk"]
                risk_icon = {"High": "\U0001f534", "Medium": "\U0001f7e1", "Low": "\U0001f7e2"}.get(risk, "\u26aa")
                notes = cd.get("preemption_notes", "")
                if risk == "High" and notes:
                    st.warning(f"{risk_icon} **Preemption risk: {risk}** \u2014 {notes}")
                elif risk != "Low":
                    st.markdown(f"{risk_icon} **Preemption risk: {risk}**")
        else:
            cats = b.get("material_categories") or []
            col_a, col_b = st.columns(2)
            with col_a:
                if cats:
                    st.markdown(f"**Materials:** {', '.join(c.replace('_', ' ').title() for c in cats)}")
                st.markdown(f"**Instrument:** {(b.get('instrument_type') or '\u2014').replace('_', ' ').title()}")
            with col_b:
                st.markdown(f"**Last action:** {b.get('last_action_date') or '\u2014'}")

        if b.get("source_url"):
            st.markdown(f"[View official source \u2197]({b['source_url']})")

else:
    st.info("No bills match the current filters.")
