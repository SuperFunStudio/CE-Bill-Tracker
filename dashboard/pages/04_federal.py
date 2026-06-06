"""
SignalScout — Federal Actions Tracker
Federal Register documents, Executive Orders, DOJ actions, and preemption risk analysis.
"""
import json
import os
from datetime import date

import httpx
import streamlit as st

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from styles import inject_shared_styles

st.set_page_config(page_title="SignalScout — Federal Actions", page_icon="🔭", layout="wide")

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

inject_shared_styles()
st.markdown("""
<style>
/* Preemption alert banner */
.preemption-banner {
    background: linear-gradient(90deg, #450a0a, #7f1d1d);
    border: 1px solid #dc2626;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    color: #fecaca;
}
.preemption-banner strong { color: #fca5a5; }
.preemption-banner .title { color: #fef2f2; font-size: 1.1rem; font-weight: 700; margin-bottom: 0.3rem; }

/* Federal action card */
.fed-card {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    display: flex;
    justify-content: space-between;
    gap: 2rem;
}
.fed-card .main { flex: 1; }
.fed-card .title-text { color: #f3f4f6; font-size: 1.15rem; font-weight: 600; margin-bottom: 0.4rem; }
.fed-card .meta { color: #6b7280; font-size: 0.875rem; margin-bottom: 0.6rem; }
.fed-card .meta span { margin-right: 1rem; }
.fed-card .summary { color: #9ca3af; font-size: 0.925rem; line-height: 1.5; }
.fed-card .risk-panel { text-align: right; min-width: 160px; }
.fed-card .risk-label { color: #6b7280; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
.fed-card .risk-value { font-size: 1.6rem; font-weight: 700; line-height: 1.2; }
.risk-high { color: #ef4444; }
.risk-medium { color: #f59e0b; }
.risk-low { color: #22c55e; }
.risk-none { color: #6b7280; }

.fed-card .comment-deadline { color: #60a5fa; font-size: 0.85rem; margin-top: 0.3rem; }
.fed-card .view-link { display: inline-block; margin-top: 0.5rem; }
.fed-card .view-link a {
    color: #60a5fa; text-decoration: none; font-size: 0.85rem;
}
.fed-card .view-link a:hover { text-decoration: underline; }

/* Type badges */
.type-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-right: 0.5rem;
}
.badge-proposed_rule { background: #1e3a5f; color: #93c5fd; }
.badge-final_rule { background: #052e16; color: #86efac; }
.badge-notice { background: #422006; color: #fbbf24; }
.badge-executive_order { background: #4a1d1d; color: #fca5a5; }
.badge-federal_bill { background: #2d1b4e; color: #c4b5fd; }

/* Litigation cards */
.lit-card {
    background: #0f172a;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.75rem;
}
.lit-card .case-name { color: #93c5fd; font-size: 1.05rem; font-weight: 600; }
.lit-card .case-meta { color: #6b7280; font-size: 0.85rem; margin: 0.3rem 0 0.5rem; }
.lit-card .case-meta span { margin-right: 1rem; }
.lit-card .risk-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}
.status-active { background: #064e3b; color: #6ee7b7; }
.status-terminated { background: #1f2937; color: #9ca3af; }
.status-injunction_granted { background: #7f1d1d; color: #fca5a5; }
.status-injunction_denied { background: #064e3b; color: #6ee7b7; }
.status-appealed { background: #1e3a5f; color: #93c5fd; }
.challenge-dormant_commerce_clause { background: #3b0764; color: #d8b4fe; }
.challenge-preemption { background: #7c2d12; color: #fdba74; }
.challenge-due_process { background: #1e3a5f; color: #93c5fd; }
.challenge-other { background: #1f2937; color: #9ca3af; }

.event-critical { border-left: 3px solid #ef4444; padding-left: 0.75rem; }
.event-high { border-left: 3px solid #f59e0b; padding-left: 0.75rem; }
.event-medium { border-left: 3px solid #3b82f6; padding-left: 0.75rem; }
.event-low { border-left: 3px solid #374151; padding-left: 0.75rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def fetch_federal_actions():
    try:
        resp = httpx.get(
            f"{API_BASE}/federal-actions",
            params={"limit": 100, "days_back": 730},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch federal actions: {e}")
        return []


@st.cache_data(ttl=300)
def fetch_litigation_cases():
    try:
        resp = httpx.get(f"{API_BASE}/litigation-cases", params={"limit": 100}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_litigation_case_detail(case_id: int):
    try:
        resp = httpx.get(f"{API_BASE}/litigation-cases/{case_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# —— Sidebar ————————————————————————————————————————————————
with st.sidebar:
    st.markdown("### Filters")
    action_types = ["All", "proposed_rule", "final_rule", "notice", "executive_order", "federal_bill"]
    filter_type = st.selectbox("Action Type", action_types, format_func=lambda x: x.replace("_", " ").title())
    filter_risk = st.selectbox("Preemption Risk", ["All", "High", "Medium", "Low"])

    st.markdown("---")
    st.markdown("### Litigation Filters")
    filter_lit_status = st.selectbox(
        "Case Status",
        ["All", "active", "injunction_granted", "injunction_denied", "appealed", "terminated"],
        format_func=lambda x: x.replace("_", " ").title() if x != "All" else x,
    )
    filter_lit_state = st.text_input("State (e.g. CA)", max_chars=2).upper() or None


st.title("🏛️ Federal Actions Tracker")
st.caption("Federal Register documents, Executive Orders, and DOJ actions affecting EPR.")


# —— Preemption Alert Banner ————————————————————————————————
st.markdown("""
<div class="preemption-banner">
    <div class="title">⚠️ Federal Preemption Watch</div>
    <p>
        The administration is actively pursuing environmental deregulation at the federal level.
        The <strong>Oregon NAW case</strong> (trial July 13, 2026) could set precedent for Dormant Commerce Clause
        challenges against all state packaging EPR programs. The <strong>PACK Act</strong> (introduced Dec 2025) includes
        explicit state preemption provisions for packaging labeling. The <strong>DOJ/NEC RFI</strong> (Aug 2025) is
        seeking state laws that adversely affect the national economy — packaging EPR laws could be targeted.
    </p>
</div>
""", unsafe_allow_html=True)


# —— Fetch and filter —————————————————————————————————————
actions = fetch_federal_actions()

if filter_type != "All":
    actions = [a for a in actions if a.get("action_type") == filter_type]
if filter_risk != "All":
    actions = [a for a in actions if a.get("preemption_risk") == filter_risk]

# Sort: high preemption risk first, then by date
risk_order = {"High": 0, "Medium": 1, "Low": 2, None: 3}
actions.sort(key=lambda a: (risk_order.get(a.get("preemption_risk"), 3), -(a.get("published_date") or "0000") > "0"))


# —— Fetch litigation data ————————————————————————————————————
lit_cases = fetch_litigation_cases()
if filter_lit_status != "All":
    lit_cases = [c for c in lit_cases if c.get("case_status") == filter_lit_status]
if filter_lit_state:
    lit_cases = [c for c in lit_cases if c.get("related_state") == filter_lit_state]


# —— Metrics row 1: Federal Register ————————————————————————
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Actions", len(actions))
col2.metric("High Risk", len([a for a in actions if a.get("preemption_risk") == "High"]))
col3.metric("Open Comment", len([
    a for a in actions
    if a.get("comment_deadline") and a["comment_deadline"] >= date.today().isoformat()
]))
col4.metric("This Year", len([
    a for a in actions
    if (a.get("published_date") or "")[:4] == str(date.today().year)
]))

# —— Metrics row 2: Litigation ————————————————————————————————
st.markdown("**Active Litigation**")
lcol1, lcol2, lcol3 = st.columns(3)
lcol1.metric(
    "Active Federal Cases",
    len([c for c in lit_cases if c.get("case_status") == "active"]),
)
lcol2.metric(
    "Injunctions in Effect",
    len([c for c in lit_cases if c.get("case_status") == "injunction_granted"]),
)
lcol3.metric(
    "High-Risk Laws (≥70)",
    len([c for c in lit_cases if (c.get("preemption_risk") or 0) >= 70]),
)


# —— Action cards —————————————————————————————————————————
if not actions:
    st.info("No federal actions match the current filters. The Federal Register pipeline fetches new documents automatically.")
else:
    for action in actions:
        title = action.get("title") or "Untitled"
        agency = action.get("agency") or "Unknown Agency"
        action_type = action.get("action_type") or "notice"
        pub_date = action.get("published_date") or "—"
        risk = action.get("preemption_risk") or "—"
        summary = action.get("ai_summary") or ""
        doc_url = action.get("document_url") or ""
        comment_dl = action.get("comment_deadline")

        # Risk styling
        risk_class = f"risk-{risk.lower()}" if risk in ("High", "Medium", "Low") else "risk-none"

        # Type badge
        badge_class = f"badge-{action_type}" if action_type in ("proposed_rule", "final_rule", "notice", "executive_order", "federal_bill") else "badge-notice"

        # Comment deadline info
        comment_html = ""
        if comment_dl:
            try:
                dl_date = date.fromisoformat(comment_dl[:10])
                days_left = (dl_date - date.today()).days
                if days_left > 0:
                    comment_html = f'<div class="comment-deadline">💬 Comment deadline: {comment_dl} ({days_left}d left)</div>'
                elif days_left == 0:
                    comment_html = '<div class="comment-deadline" style="color:#ef4444;">💬 Comment deadline: TODAY</div>'
                else:
                    comment_html = f'<div class="comment-deadline" style="color:#6b7280;">💬 Comment period closed ({comment_dl})</div>'
            except ValueError:
                pass

        link_html = ""
        if doc_url:
            link_html = f'<div class="view-link"><a href="{doc_url}" target="_blank">View Document →</a></div>'

        st.markdown(f"""
        <div class="fed-card">
            <div class="main">
                <div class="title-text">{title}</div>
                <div class="meta">
                    <span class="type-badge {badge_class}">{action_type.replace('_', ' ').title()}</span>
                    <span>{agency}</span>
                    <span>Published: {pub_date}</span>
                </div>
                <div class="summary">{summary}</div>
                {comment_html}
                {link_html}
            </div>
            <div class="risk-panel">
                <div class="risk-label">Preemption Risk</div>
                <div class="risk-value {risk_class}">{risk}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# —— Litigation Cases section ————————————————————————————————
st.markdown("---")
with st.expander(f"⚖️ Active Litigation ({len(lit_cases)} cases)", expanded=bool(lit_cases)):
    if not lit_cases:
        st.info("No litigation cases tracked yet. Run `scripts/seed_courtlistener.py` to backfill known EPR cases.")
    else:
        COURT_NAMES = {
            "cacd": "C.D. California", "cand": "N.D. California", "caed": "E.D. California",
            "casd": "S.D. California", "ord": "D. Oregon", "wawd": "W.D. Washington",
            "dcd": "D.D.C.", "nyd": "S.D. New York", "nynd": "N.D. New York",
            "mnd": "D. Minnesota", "cod": "D. Colorado", "med": "D. Maine",
        }

        for case in lit_cases:
            case_id = case.get("id")
            case_name = case.get("case_name", "Unknown Case")
            court_id = case.get("court_id", "")
            court_display = COURT_NAMES.get(court_id, court_id.upper() if court_id else "Federal Court")
            status = case.get("case_status", "unknown")
            challenge = case.get("challenge_type", "other")
            state = case.get("related_state") or "—"
            preemption_risk = case.get("preemption_risk") or 0
            last_activity = case.get("last_activity_date") or "—"
            cl_url = case.get("cl_url") or ""
            plaintiffs = case.get("key_plaintiffs") or []
            event_count = case.get("event_count", 0)

            status_class = f"status-{status}"
            challenge_class = f"challenge-{challenge}"

            plaintiffs_html = ""
            if plaintiffs:
                tags = "".join(
                    f'<span style="background:#1f2937;color:#d1d5db;padding:1px 6px;border-radius:4px;font-size:0.75rem;margin-right:4px;">{p}</span>'
                    for p in (plaintiffs[:3] if isinstance(plaintiffs, list) else [str(plaintiffs)])
                )
                plaintiffs_html = f'<div style="margin-top:0.4rem;">{tags}</div>'

            name_html = (
                f'<a href="{cl_url}" target="_blank" style="color:#93c5fd;text-decoration:none;">{case_name}</a>'
                if cl_url else f'<span style="color:#93c5fd;">{case_name}</span>'
            )

            risk_color = "#ef4444" if preemption_risk >= 70 else "#f59e0b" if preemption_risk >= 40 else "#22c55e"

            st.markdown(f"""
            <div class="lit-card">
                <div class="case-name">{name_html}</div>
                <div class="case-meta">
                    <span>🏛️ {court_display}</span>
                    <span>📍 {state}</span>
                    <span>Last activity: {last_activity}</span>
                    <span>{event_count} filings</span>
                </div>
                <span class="risk-pill {status_class}">{status.replace('_', ' ').title()}</span>&nbsp;
                <span class="risk-pill {challenge_class}">{challenge.replace('_', ' ').title()}</span>&nbsp;
                <span style="color:{risk_color};font-weight:700;font-size:0.9rem;">Risk: {preemption_risk}/100</span>
                {plaintiffs_html}
            </div>
            """, unsafe_allow_html=True)

            # Case timeline expander
            if case_id:
                with st.expander(f"📋 Timeline — {case_name[:60]}"):
                    detail = fetch_litigation_case_detail(case_id)
                    if detail and detail.get("events"):
                        events = sorted(detail["events"], key=lambda e: e.get("date_filed") or "")
                        for ev in events:
                            sig = ev.get("significance", "low")
                            ev_class = f"event-{sig}"
                            sig_label = {"critical": "🚨 CRITICAL", "high": "⚠️ HIGH", "medium": "ℹ️ MEDIUM", "low": "· LOW"}.get(sig, sig.upper())
                            st.markdown(f"""
                            <div class="{ev_class}" style="margin-bottom:0.6rem;padding:0.5rem 0.75rem;background:#0f172a;border-radius:4px;">
                                <div style="color:#6b7280;font-size:0.8rem;">{ev.get('date_filed','?')} · {ev.get('event_type','').replace('_',' ').title()} · <strong>{sig_label}</strong></div>
                                <div style="color:#d1d5db;font-size:0.9rem;margin-top:0.25rem;">{ev.get('summary') or ev.get('description') or '—'}</div>
                                {"<a href='" + ev['document_url'] + "' target='_blank' style='color:#60a5fa;font-size:0.8rem;'>View Document →</a>" if ev.get('document_url') else ""}
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.caption("No events recorded yet for this case.")


# —— Context section ————————————————————————————————————————
st.markdown('<div class="section-header">Federal Preemption Context</div>', unsafe_allow_html=True)

st.markdown("""
**Why federal tracking matters for EPR:**

Federal deregulation is *accelerating* state-level EPR action, not slowing it. States are the primary venue for
circular economy regulation. But federal preemption risk is real and must be tracked.

**Key federal vectors to watch:**

- **Oregon NAW Case** (trial July 13, 2026): National Association of Wholesaler-Distributors challenging OR SB 582
  under the Dormant Commerce Clause. If successful, could provide a template to challenge all state packaging EPR programs.

- **PACK Act** (introduced Dec 2025): Federal bill with explicit state preemption provisions for packaging labeling.
  Would override laws like CA SB 343.

- **DOJ/NEC RFI** (Aug 2025): Request for Information seeking state laws that "significantly and adversely affect the
  national economy." Packaging EPR laws are potential targets.

- **EPA Battery EPR Framework**: Voluntary national battery EPR framework expected Summer 2026. Could establish a
  federal floor below which states cannot go.

- **Dormant Commerce Clause**: The administration has shown willingness to use DCC challenges against state
  environmental laws (see DOJ suit against California egg standards).
""")
