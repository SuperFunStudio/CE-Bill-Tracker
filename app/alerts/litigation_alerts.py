"""Subject + body for a CourtListener-sourced litigation alert, shared by both dispatch paths.

Two places emit these — the CourtListener webhook (app/api/webhooks.py) and the docket refresh cycle
(app/scheduler/jobs.py) — and each used to hand-roll its own body. They drifted, and both carried two
problems:

  1. **Markdown that only worked on one channel.** The same string goes to Slack (mrkdwn) and to email
     (HTML). `**Date**:` renders bold in Slack and prints literal asterisks in the email. So the body
     here is plain prose with no emphasis markers — the email shell supplies the styling, and Slack
     loses only bold.
  2. **The reader was sent straight to CourtListener.** A raw docket URL skips past everything we
     know about the case (preemption risk, the state law it challenges, the event timeline) and hands
     a cold external domain the click. Alerts now lead to the case's Atlas Circular page, which
     carries the CourtListener link for anyone who wants the primary source.

The body deliberately contains no URLs at all: the caller passes `litigation_case_url(case.id)` as
the CTA, which the email renders as a button and Slack appends as a bare link.
"""
from __future__ import annotations

from typing import Any

# Reader-facing labels for the significance tiers the classifier emits.
_CRITICAL = "critical"


def _court_label(case: Any) -> str:
    """Prefer the court's real name — "COD" means nothing to a compliance reader; "U.S. District
    Court, D. Colo." does. The code is the fallback for rows we only have an id for."""
    name = (getattr(case, "court_name", None) or "").strip()
    if name:
        return name
    return case.court_id.upper() if getattr(case, "court_id", None) else "Federal Court"


def _event_label(event_type: str | None) -> str:
    return (event_type or "docket event").replace("_", " ").title()


def render_litigation_subject(case: Any, significance: str | None) -> str:
    """Subject line. An injunction is the one outcome that changes what a compliance team must do
    tomorrow, so it leads; otherwise the severity leads in words.

    No emoji. A siren in a subject line is a mild spam-filter signal, it renders as tofu in some
    clients, and it spends the most valuable characters we own on decoration — "ENFORCEMENT STAYED"
    already carries every bit of the urgency a 🚨 was doing. `significance` still shapes the line, it
    just says the word instead of drawing it.
    """
    if getattr(case, "case_status", None) == "injunction_granted":
        return f"ENFORCEMENT STAYED — EPR Litigation Update: {case.case_name}"
    prefix = "CRITICAL — " if (significance or "").lower() == _CRITICAL else ""
    return f"{prefix}EPR Litigation Update: {case.case_name}"


def render_litigation_kicker(date_filed: Any = None) -> str:
    """The masthead edition line: what this is, and how fresh. Falls back to the classification alone
    when the event carries no date (rather than printing an empty separator)."""
    if not date_filed:
        return "LITIGATION ALERT"
    try:
        stamp = date_filed.strftime("%d %B %Y").lstrip("0").upper()
    except AttributeError:  # already a string from the source payload
        stamp = str(date_filed).upper()
    return f"LITIGATION ALERT · {stamp}"


def render_litigation_preheader(
    case: Any, event_type: str | None, significance: str | None = None
) -> str:
    """Inbox preview text — the line Gmail shows beside the subject.

    The subject already names the case, so this spends its words on what a reader actually decides
    on: what happened and whether enforcement is affected. Kept under ~90 characters, past which
    clients truncate.
    """
    # Lead on the JURISDICTION whose law is under challenge, not the court hearing it: the reader
    # subscribed by state, so "Colorado EPR" is what tells them this is theirs.
    scope = f"{case.related_state} EPR" if getattr(case, "related_state", None) else "EPR law"
    if getattr(case, "case_status", None) == "injunction_granted":
        # Nothing competes with a stay for the reader's attention.
        return f"{scope} — enforcement is stayed. What it changes for your compliance timeline."
    lead = _event_label(event_type).lower()
    if (significance or "").lower() == _CRITICAL:
        return f"{scope} — {lead} filed; a critical step toward halting enforcement."
    return f"{scope} — {lead} filed. The filing, the risk score, and what happens next."


def render_litigation_body(
    case: Any,
    *,
    event_type: str | None,
    date_filed: Any = None,
    significance: str | None = None,
    summary: str | None = None,
) -> str:
    """Channel-neutral body: plain prose, no markdown, no URLs (the CTA carries the link).

    Kept deliberately short — the alert's job is to say what happened and get the reader onto the
    case page, not to reproduce the docket.
    """
    prefix = (
        "ENFORCEMENT STAYED — "
        if getattr(case, "case_status", None) == "injunction_granted"
        else ""
    )
    lines = [
        f"{prefix}{_event_label(event_type)} in {case.case_name} ({_court_label(case)}).",
        "",
    ]
    if date_filed:
        lines.append(f"Filed: {date_filed}")
    if significance:
        lines.append(f"Significance: {significance.upper()}")
    if getattr(case, "preemption_risk", None) is not None:
        lines.append(f"Preemption risk: {case.preemption_risk}/100")
    if summary:
        lines += ["", summary]
    lines += [
        "",
        "The case page has the full docket timeline, the state law it challenges, and a link to the "
        "filing on CourtListener.",
    ]
    return "\n".join(lines)
