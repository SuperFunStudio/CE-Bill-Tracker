"""Render EVERY outbound email template in app/alerts/ with SYNTHETIC data and send one
sample of each to a single hardcoded recipient.

Visual / deliverability test for the Atlas Circular rebrand. This NEVER touches the database
and NEVER emails a real subscriber: the recipient is hardcoded to kenny@superfun.studio and
the from-address is forced to alerts@atlascircular.com.

Run:  venv/Scripts/python.exe scripts/send_email_samples.py
"""
from __future__ import annotations

# --- Environment MUST be set before any app.* import (pydantic Settings reads env at import time).
import os

from dotenv import load_dotenv

load_dotenv()  # pull the prod SENDGRID_API_KEY (and everything else) out of .env first
# ...then override the from-address so it wins over whatever .env carries.
os.environ["SENDGRID_FROM_EMAIL"] = "alerts@atlascircular.com"

import asyncio
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Ensure the repo root is importable when run as `python scripts/send_email_samples.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- App imports (env is now locked in) ----------------------------------------------------------
from app.alerts import access_emails, auth_emails, deadline_alerts, digest as digest_mod
from app.alerts import litigation_alerts
from app.alerts.applinks import litigation_case_url, subscribe_url
from app.alerts.unsubscribe import unsubscribe_url
from app.alerts import new_bill_alerts, trial_reminders, watchlist_onboarding, watchlist_recap
from app.alerts import welcome_email
from app.alerts.sendgrid_sender import SendGridSender, _build_email_html, build_text_alert_html
from app.alerts.welcome_email import StandingRow, StateOfPlay

RECIPIENT = "kenny@superfun.studio"  # ALWAYS and ONLY this address
SUBJECT_PREFIX = "[Atlas sample] "
# Synthetic litigation case id for the sample alert's in-app CTA. Points at a real route
# (/federal?case=…) with an id that won't resolve — the button's styling and target are what's under
# review here, not the landing content.
SAMPLE_CASE_ID = 9001
# Signed into the sample unsubscribe link. Deliberately an id that doesn't exist, so clicking the
# footer button in a sample can't unsubscribe a real row.
SAMPLE_SUBSCRIPTION_ID = 999_999
OUT_DIR = Path(r"c:\Users\kenny\SignalScout\tmp\email_samples")


# --- Synthetic fixtures --------------------------------------------------------------------------
def make_bill(
    *,
    id: int,
    state: str,
    bill_number: str,
    title: str,
    status: str = "introduced",
    instrument_type: str = "epr",
    materials=None,
    confidence: float = 0.88,
    ai_summary: str | None = None,
    action_date: date | None = None,
    policy_stance: str | None = None,
    urgency: str | None = "medium",
    source_url: str = "https://legiscan.com/CA/bill/SB54/2024",
):
    return types.SimpleNamespace(
        id=id,
        state=state,
        bill_number=bill_number,
        title=title,
        status=status,
        instrument_type=instrument_type,
        material_categories=materials if materials is not None else ["packaging", "plastics"],
        confidence_score=confidence,
        ai_summary=ai_summary,
        last_action_date=action_date,
        status_date=action_date,
        policy_stance=policy_stance,
        urgency=urgency,
        source_url=source_url,
        region="US",
    )


def make_sub(
    *,
    id: int = 4242,
    email: str = RECIPIENT,
    organization: str | None = "Superfun Studio",
    states=None,
    instrument_types=None,
    material_categories=None,
    scope: str = "filter",
    firebase_uid: str | None = None,
):
    return types.SimpleNamespace(
        id=id,
        email=email,
        organization=organization,
        states=states if states is not None else ["CA", "OR", "ME"],
        instrument_types=instrument_types if instrument_types is not None else ["epr", "packaging"],
        material_categories=material_categories if material_categories is not None else ["packaging"],
        region_scope=None,
        scope=scope,
        firebase_uid=firebase_uid,
        min_confidence=0.0,
        alert_on=["deadline"],
    )


def sample_bills():
    return [
        make_bill(
            id=101, state="CA", bill_number="SB 54", status="enacted", policy_stance="advances",
            title="Plastic Pollution Producer Responsibility Act — packaging EPR with source-reduction targets",
            ai_summary="Establishes a producer responsibility organization for single-use packaging and "
                       "sets 25% source-reduction and 65% recycling targets by 2032.",
            action_date=date(2026, 6, 12), confidence=0.94,
            materials=["packaging", "plastics"],
        ),
        make_bill(
            id=102, state="OR", bill_number="HB 3220", status="passed_chamber", policy_stance="advances",
            title="Right to Repair for consumer electronics — parts, tools, and documentation mandate",
            instrument_type="right_to_repair", materials=["electronics"],
            action_date=date(2026, 5, 30), confidence=0.81, urgency="high",
        ),
        make_bill(
            id=103, state="ME", bill_number="LD 1541", status="in_committee",
            title="Extended Producer Responsibility for packaging — stewardship program and eco-modulated fees",
            action_date=date(2026, 6, 3), confidence=0.77,
        ),
    ]


# --- Template registry ---------------------------------------------------------------------------
# Each entry: (label, kind, builder) where builder() -> (subject, payload).
#   kind "html" -> payload sent via send_html(to, subject, html)
#   kind "text" -> payload sent via send_text_alert(to, subject, body_text)
def build_registry():
    reg = []

    # 1. Per-bill status-change alert (sendgrid_sender._build_email_html).
    def _per_bill():
        bill = make_bill(
            id=101, state="CA", bill_number="SB 54", status="enacted", policy_stance="advances",
            title="Plastic Pollution Producer Responsibility Act",
            ai_summary="Signed into law: a producer responsibility organization must be operational for "
                       "single-use packaging, with source-reduction and recycling targets phasing in.",
            action_date=date(2026, 6, 12), confidence=0.94, materials=["packaging", "plastics"],
        )
        changes = [
            types.SimpleNamespace(
                change_type="status_change",
                old_value={"status": "passed_chamber"},
                new_value={"status": "enacted"},
            ),
            types.SimpleNamespace(change_type="text_update", old_value=None, new_value=None),
        ]
        html = _build_email_html(bill, changes, litigation_context="")
        return "CA SB 54 — Legislative Update", html

    reg.append(("per_bill_status_alert", "html", _per_bill))

    # 2. Litigation text alert (send_text_alert) — rendered through the SHARED renderer both live
    # dispatch paths use (CourtListener webhook + docket refresh cycle), so the sample shows the real
    # thing: plain prose, no markdown leaking through, and no CourtListener URL in the body. The
    # in-app case link rides as the CTA button (see TEXT_ALERT_CTA below).
    def _litigation():
        case = types.SimpleNamespace(
            id=SAMPLE_CASE_ID,
            case_name="Nat'l Ass'n of Wholesaler-Distributors v. Maryland Dep't of the Environment",
            court_id="mdd",
            case_status="active",
            preemption_risk=62,
            cl_url="https://www.courtlistener.com/docket/00000000/naw-v-mde/",
        )
        subject = litigation_alerts.render_litigation_subject(case, "critical")
        body = litigation_alerts.render_litigation_body(
            case,
            event_type="order_on_motion",
            date_filed=date(2026, 6, 18),
            significance="critical",
            summary="The court denied the trade association's motion for a preliminary injunction, so "
                    "the stewardship-plan filing deadline stands. Producers should keep preparing "
                    "their plans; the January filing date is unchanged pending appeal.",
        )
        return subject, body

    reg.append(("litigation_text_alert", "text", _litigation))

    # 3. Account signup welcome.
    reg.append((
        "account_welcome", "html",
        lambda: (welcome_email.render_account_welcome_subject(),
                 welcome_email.render_account_welcome_html()),
    ))

    # 4. Pro welcome — trial + founding.
    reg.append((
        "pro_welcome_trial_founding", "html",
        lambda: (welcome_email.render_pro_welcome_subject(is_trial=True),
                 welcome_email.render_pro_welcome_html(is_trial=True, founding=True)),
    ))

    # 5. Pro welcome — active paid, non-founding.
    reg.append((
        "pro_welcome_active", "html",
        lambda: (welcome_email.render_pro_welcome_subject(is_trial=False),
                 welcome_email.render_pro_welcome_html(is_trial=False, founding=False)),
    ))

    # 6. Complimentary Pro grant.
    reg.append((
        "comp_grant", "html",
        lambda: (welcome_email.render_comp_grant_subject(),
                 welcome_email.render_comp_grant_html("30 days", name="Kenny")),
    ))

    # 7. Payment failed (dunning).
    reg.append((
        "payment_failed", "html",
        lambda: (welcome_email.render_payment_failed_subject(),
                 welcome_email.render_payment_failed_html()),
    ))

    # 8. Subscription canceled.
    reg.append((
        "subscription_canceled", "html",
        lambda: (welcome_email.render_subscription_canceled_subject(),
                 welcome_email.render_subscription_canceled_html()),
    ))

    # 9. Referral reward.
    reg.append((
        "referral_reward", "html",
        lambda: (welcome_email.render_referral_reward_subject(30),
                 welcome_email.render_referral_reward_html(30)),
    ))

    # 10. Subscription welcome (windowed recent-activity roundup).
    def _subscription_welcome():
        sub = make_sub()
        bills = sample_bills()
        enacted = [b for b in bills if b.status in ("enacted", "signed")]
        active = [b for b in bills if b.status not in ("enacted", "signed", "failed", "vetoed")]
        sop = StateOfPlay(
            scope_total=len(bills),
            enacted_recent=len(enacted),
            active_recent=len(active),
            by_state=[
                StandingRow(label="CA", enacted=1, active=2),
                StandingRow(label="OR", enacted=0, active=1),
                StandingRow(label="ME", enacted=0, active=1),
            ],
            by_topic=[
                StandingRow(label="Extended Producer Responsibility", enacted=1, active=1),
                StandingRow(label="Right to Repair", enacted=0, active=1),
            ],
            recent_enacted=enacted,
            recent_movement=active,
        )
        # Mirrors the live prod aggregate at the time of writing, so the sample reads true.
        corpus = welcome_email.CorpusStats(
            total_bills=2544, enacted_laws=1178, regions=37, year_bills=368, year=2026
        )
        # A stand-in for the LLM catch-up paragraph, written the way the retuned prompt asks for it:
        # named laws, the obligation each creates, and what's worth a calendar entry.
        recap = (
            "Vermont's H-915 stands up a beverage-container EPR program, and Oregon HB-4144 puts "
            "battery stewardship obligations onto producers. If you place either of those product "
            "types on shelves in those states, a registration or reporting obligation now attaches "
            "to you.\n\n"
            "Two more are worth a calendar entry. California SB-1180 and New York S-1464 both "
            "target packaging producer responsibility in the two largest US consumer markets, and "
            "both are still moving."
        )
        window = (date(2026, 2, 1), date(2026, 8, 1))
        html = welcome_email.render_welcome_html(
            sub, sop, "August 2026", recap=recap, corpus=corpus, window=window
        )
        return welcome_email.render_welcome_subject(sop, window[0]), html

    reg.append(("subscription_welcome", "html", _subscription_welcome))

    # 11. Periodic digest.
    def _digest():
        sub = make_sub()
        bills = sample_bills()
        status_changes = [
            digest_mod.StatusChangeItem(
                bill=bills[0], old_status="passed_chamber", new_status="enacted",
                detected_at=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc),
            ),
            digest_mod.StatusChangeItem(
                bill=bills[1], old_status="in_committee", new_status="passed_chamber",
                detected_at=datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc),
            ),
        ]
        fed = types.SimpleNamespace(
            agency="EPA", title="Draft framework for a national packaging recyclability standard",
            document_url="https://www.federalregister.gov/documents/2026/06/01/epa-packaging",
            preemption_risk="medium", material_categories=["packaging"],
        )
        content = digest_mod.DigestContent(
            status_changes=status_changes,
            new_bills=[bills[2]],
            federal_actions=[fed],
            status_overflow=3, new_overflow=0, federal_overflow=0,
        )
        html = digest_mod.render_digest_html(sub, content, "month")
        return digest_mod.render_digest_subject(content, "month"), html

    reg.append(("digest", "html", _digest))

    # Shared deadline fixture builders.
    def _make_deadline(id, bill, state, dtype, desc, who, dl_date):
        return types.SimpleNamespace(
            id=id, bill=bill, state=state, region="US", federal_action_id=None,
            deadline_type=dtype, description=desc, who_affected=who,
            deadline_date=dl_date, source_url="https://www.atlascircular.com/compliance",
        )

    # 12. Deadline alert — single.
    def _deadline_single():
        sub = make_sub()
        b = sample_bills()[0]
        d = _make_deadline(
            9001, b, "CA", "plan_submission",
            "Producers must submit a stewardship plan to the appointed PRO.",
            "Any producer of covered single-use packaging sold into California.",
            date.today() + timedelta(days=21),
        )
        content = deadline_alerts.DeadlineAlertContent(
            items=[deadline_alerts.DeadlineItem(deadline=d, days_until=21)]
        )
        html = deadline_alerts.render_deadline_alert_html(sub, content)
        return deadline_alerts.render_deadline_alert_subject(content), html

    reg.append(("deadline_single", "html", _deadline_single))

    # 13. Deadline alert — multiple (total=3).
    def _deadline_multi():
        sub = make_sub()
        bills = sample_bills()
        items = [
            deadline_alerts.DeadlineItem(
                deadline=_make_deadline(
                    9002, bills[0], "CA", "plan_submission",
                    "Stewardship plan due to the packaging PRO.",
                    "Covered-packaging producers.", date.today() + timedelta(days=5),
                ), days_until=5,
            ),
            deadline_alerts.DeadlineItem(
                deadline=_make_deadline(
                    9003, bills[2], "ME", "registration",
                    "Producer registration and initial fee payment window opens.",
                    "Brand owners over the de-minimis revenue threshold.",
                    date.today() + timedelta(days=40),
                ), days_until=40,
            ),
            deadline_alerts.DeadlineItem(
                deadline=_make_deadline(
                    9004, None, "WA", "reporting",
                    "Annual recycled-content reporting is due to the Department of Ecology.",
                    "Beverage and household-product producers.",
                    date.today() + timedelta(days=68),
                ), days_until=68,
            ),
        ]
        content = deadline_alerts.DeadlineAlertContent(items=items)
        html = deadline_alerts.render_deadline_alert_html(sub, content)
        return deadline_alerts.render_deadline_alert_subject(content), html

    reg.append(("deadline_multi", "html", _deadline_multi))

    # 14. New-bill alert.
    def _new_bill():
        sub = make_sub()
        content = new_bill_alerts.NewBillAlertContent(bills=sample_bills())
        html = new_bill_alerts.render_new_bill_alert_html(sub, content)
        return new_bill_alerts.render_new_bill_alert_subject(content), html

    reg.append(("new_bill_alert", "html", _new_bill))

    # 15. Trial-ending reminder.
    def _trial_reminder():
        ent = types.SimpleNamespace(
            email=RECIPIENT,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=3),
        )
        item = trial_reminders.TrialReminderItem(entitlement=ent, days_until=3)
        html = trial_reminders.render_trial_reminder_html(item)
        return trial_reminders.render_trial_reminder_subject(item), html

    reg.append(("trial_reminder", "html", _trial_reminder))

    # 16. Watch-list onboarding.
    def _onboarding():
        sub = make_sub(scope="watchlist", firebase_uid="synthetic-uid")
        content = watchlist_onboarding.OnboardingContent(
            sub=sub,
            bills=sample_bills(),
            bill_overflow=2,
            topics=["epr", "right_to_repair"],
            states=["CA", "OR"],
            retention_until=datetime.now(timezone.utc) + timedelta(days=365),
        )
        html = watchlist_onboarding.render_onboarding_html(content)
        return watchlist_onboarding.render_onboarding_subject(content), html

    reg.append(("watchlist_onboarding", "html", _onboarding))

    # 17. Watch-list recap.
    def _recap():
        sub = make_sub(scope="watchlist", firebase_uid="synthetic-uid")
        content = watchlist_recap.RecapContent(
            sub=sub,
            new_bills=sample_bills()[:2],
            new_overflow=0,
            total_watched=7,
        )
        html = watchlist_recap.render_recap_html(content)
        return watchlist_recap.render_recap_subject(content), html

    reg.append(("watchlist_recap", "html", _recap))

    # 18. Access request — confirmation (auto-reply).
    reg.append((
        "access_confirmation", "html",
        lambda: (access_emails.render_confirmation_subject("pro"),
                 access_emails.render_confirmation_html("Kenny", "pro")),
    ))

    # 19. Access request — team notification (lead).
    reg.append((
        "access_notification", "html",
        lambda: (
            access_emails.render_notification_subject(RECIPIENT, "enterprise"),
            access_emails.render_notification_html(
                email=RECIPIENT, name="Kenny", organization="Superfun Studio",
                plan="enterprise", message="Interested in API access for a compliance dashboard.",
                source="pricing-page",
                attribution={
                    "utm_source": "linkedin", "utm_medium": "social",
                    "utm_campaign": "launch", "utm_content": "eco-mod-spread-post",
                    "referrer": "https://www.linkedin.com/",
                },
            ),
        ),
    ))

    # 20/21. Account-security emails. Rendered against a SYNTHETIC action link — the real ones come
    # from firebase-admin at send time, and minting a live one here would email a working
    # verify/reset link for a real account. The link is only there to check the button + fallback
    # URL wrap; clicking it does nothing.
    fake_link = (
        "https://ce-bill-tracker.firebaseapp.com/__/auth/action?mode=verifyEmail"
        "&oobCode=SAMPLE-not-a-real-code-0000000000&apiKey=SAMPLE&lang=en"
    )
    reg.append((
        "verify_email", "html",
        lambda: (auth_emails.render_verify_subject(), auth_emails.render_verify_html(fake_link)),
    ))
    reg.append((
        "password_reset", "html",
        lambda: (auth_emails.render_reset_subject(), auth_emails.render_reset_html(fake_link)),
    ))

    return reg


def _text_alert_chrome() -> dict:
    """Everything the live litigation dispatch wraps around the body — edition line, preview text,
    CTA and footer actions. The sample is only worth reviewing if it carries the same chrome.
    The unsubscribe token is signed over a synthetic subscription id, so the link resolves to a
    "subscription not found" page rather than unsubscribing anyone real."""
    return {
        "cta_url": litigation_case_url(SAMPLE_CASE_ID),
        "kicker": litigation_alerts.render_litigation_kicker(date(2026, 6, 18)),
        "preheader": "Injunction motion in MDD — a critical step; here's what it means for enforcement.",
        "unsubscribe_url": unsubscribe_url(SAMPLE_SUBSCRIPTION_ID),
        "subscribe_url": subscribe_url("litigation_forward"),
    }


# --- Send helpers --------------------------------------------------------------------------------
async def _send(kind: str, subject: str, payload: str) -> bool:
    sender = SendGridSender()
    if kind == "text":
        return await sender.send_text_alert(RECIPIENT, subject, payload, **_text_alert_chrome())
    return await sender.send_html(RECIPIENT, subject, payload)


def _write_contact_sheet(rendered: dict, render_status: dict) -> None:
    """One page showing every template, for attaching to a compliance review.

    An ESP asks for "a content sample" and gets, at best, one screenshot of one email. This renders
    all of them stacked in iframes so the whole sending programme — what's transactional, what's
    opt-in, and the identical compliance footer on each — is legible in a single attachment. Print it
    to PDF and attach that; the iframes carry `srcdoc`, so the file stands alone with no siblings.
    """
    import html as _html

    cards = []
    for label, _kind, _builder in build_registry():
        if render_status.get(label) != "ok":
            cards.append(f"<h2>{label}</h2><p class='err'>render failed — not included</p>")
            continue
        kind, subject, payload = rendered[label]
        # The text alert's payload is prose; show the email it actually becomes, same as the file pass.
        doc = build_text_alert_html(payload, **_text_alert_chrome()) if kind == "text" else payload
        cards.append(
            f"<section><h2>{label}</h2>"
            f"<p class='subj'>Subject: {_html.escape(subject)}</p>"
            f'<iframe srcdoc="{_html.escape(doc, quote=True)}" loading="lazy"></iframe></section>'
        )
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Atlas Circular — every outbound email template</title>
<style>
 body {{ font:14px -apple-system,Segoe UI,sans-serif; background:#eceff1; margin:0; padding:32px; }}
 h1 {{ font-size:20px; margin:0 0 4px; }}
 .lede {{ color:#546e7a; max-width:60em; margin:0 0 28px; line-height:1.5; }}
 section {{ margin:0 0 34px; }}
 h2 {{ font-size:13px; letter-spacing:.08em; text-transform:uppercase; color:#37474f; margin:0 0 2px; }}
 .subj {{ color:#607d8b; margin:0 0 8px; font-size:13px; }}
 .err {{ color:#c62828; }}
 iframe {{ width:100%; max-width:680px; height:900px; border:1px solid #b0bec5; background:#fff; }}
 @media print {{ body {{ background:#fff; }} section {{ break-inside:avoid; }} }}
</style></head><body>
<h1>Atlas Circular — every outbound email template</h1>
<p class="lede">All {len(rendered)} templates this account sends, rendered with synthetic data. Every
one carries the same footer: sender identity, publisher, physical mailing address, Privacy Policy and
Terms. The opt-in editorial and alert mail additionally carries an unsubscribe button and a one-click
List-Unsubscribe header; the account-security messages (verify address, password reset) deliberately
do not, as they are transactional.</p>
{"".join(cards)}
</body></html>
"""
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")


def safe_print(line: str) -> None:
    """Print without letting the console encoding kill the run.

    Subjects carry emoji (🚨 on the deadline alerts) and the Windows console is cp1252, so a plain
    print raises UnicodeEncodeError mid-send-pass — and it did: the script died after two templates,
    inside the *exception handler* for a failed send, so the summary that would have told us WHY was
    never printed. A progress line is not worth aborting a send run for.
    """
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(line.encode(enc, "replace").decode(enc, "replace"))


def main():
    # `--render-only` stops after the dry pass: files on disk, not one API call to SendGrid. Use it
    # for anything that only changes chrome (footer, masthead, copy) — you can read the result in a
    # browser, and a render check has no business touching a sending reputation that's under review.
    render_only = "--render-only" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = build_registry()

    # --- DRY pass: render everything, write HTML/text files, print render summary ---------------
    print("=" * 72)
    print("DRY PASS — render every template + write files")
    print("=" * 72)
    rendered = {}  # label -> (kind, subject, payload)
    render_status = {}  # label -> "ok" / "render FAILED: <err>"
    for label, kind, builder in registry:
        try:
            subject, payload = builder()
            ext = "txt" if kind == "text" else "html"
            out = OUT_DIR / f"{label}.{ext}"
            out.write_text(payload, encoding="utf-8")
            if kind == "text":
                # Also write what the EMAIL actually looks like — the text body alone hides the
                # shell, the edition line, the linkified URLs, the CTA and the footer actions.
                (OUT_DIR / f"{label}.html").write_text(
                    build_text_alert_html(payload, **_text_alert_chrome()),
                    encoding="utf-8",
                )
            rendered[label] = (kind, subject, payload)
            render_status[label] = "ok"
            safe_print(f"  [render ok ] {label:<28} -> {out}")
        except Exception as e:
            render_status[label] = f"render FAILED: {e!r}"
            safe_print(f"  [render ERR] {label:<28} {e!r}")

    _write_contact_sheet(rendered, render_status)
    safe_print(f"  [contact sheet] {OUT_DIR / 'index.html'}")

    # --- SEND pass ------------------------------------------------------------------------------
    print()
    if render_only:
        print("=" * 72)
        print(f"RENDER-ONLY — nothing sent. Open {OUT_DIR} to review.")
        print("=" * 72)
        return
    print("=" * 72)
    print(f"SEND PASS — one sample of each to {RECIPIENT}")
    print("=" * 72)
    send_status = {}  # label -> "SENT ok" / "send FAILED" / "skipped (render failed)"
    for label, kind, builder in registry:
        if render_status.get(label) != "ok":
            send_status[label] = "skipped (render failed)"
            continue
        _, subject, payload = rendered[label]
        full_subject = SUBJECT_PREFIX + subject
        try:
            ok = asyncio.run(_send(kind, full_subject, payload))
            send_status[label] = "SENT ok" if ok else "send FAILED"
            safe_print(f"  [{'SENT' if ok else 'FAIL'}] {label:<28} {full_subject}")
        except Exception as e:
            send_status[label] = f"send FAILED: {e!r}"
            safe_print(f"  [ERR ] {label:<28} {e!r}")

    # --- FINAL SUMMARY --------------------------------------------------------------------------
    print()
    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    sent = failed = 0
    for label, _kind, _b in registry:
        rs = render_status.get(label, "render FAILED: not attempted")
        if rs != "ok":
            line = rs
            failed += 1
        else:
            ss = send_status.get(label, "send FAILED: not attempted")
            line = ss
            if ss == "SENT ok":
                sent += 1
            else:
                failed += 1
        print(f"  {label:<28} {line}")
    print("-" * 72)
    print(f"  {sent} sent OK, {failed} failed, {len(registry)} total")
    print(f"  HTML samples written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
