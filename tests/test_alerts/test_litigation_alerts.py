"""Litigation alerts: channel-neutral body, Atlas-first linking, and no tracked-link rewrite.

Three regressions are pinned here, all of which shipped to real inboxes:
  - markdown emphasis in a body that also goes to Slack (email printed the literal asterisks);
  - the reader being handed a raw CourtListener docket URL instead of our analysis;
  - SendGrid click tracking rewriting every href through a branded host with a broken TLS cert.
"""
import types
from datetime import date

from app.alerts.applinks import litigation_case_url, with_utm
from app.alerts.litigation_alerts import (
    render_litigation_body,
    render_litigation_kicker,
    render_litigation_preheader,
    render_litigation_subject,
)
from sendgrid.helpers.mail import Mail

from app.alerts.sendgrid_sender import (
    _apply_reply_to,
    _apply_tracking,
    _bill_block,
    _linkify,
    build_text_alert_html,
)
from app.config import settings


def _case(**kw):
    return types.SimpleNamespace(
        id=kw.get("id", 77),
        case_name=kw.get("case_name", "NAW v. Maryland DoE"),
        court_id=kw.get("court_id", "mdd"),
        case_status=kw.get("case_status", "active"),
        court_name=kw.get("court_name", None),
        related_state=kw.get("related_state", "MD"),
        preemption_risk=kw.get("preemption_risk", 62),
        cl_url=kw.get("cl_url", "https://www.courtlistener.com/docket/1/naw/"),
    )


class TestBody:
    def test_carries_no_markdown_emphasis(self):
        """The same string goes to Slack AND into an HTML email — asterisks/underscores would render
        as literal punctuation in the email."""
        body = render_litigation_body(
            _case(), event_type="order_on_motion", significance="critical", summary="Denied."
        )
        assert "**" not in body
        assert "*" not in body
        assert "_" not in body

    def test_carries_no_urls(self):
        """The link is the CTA's job. A bare docket URL in the body is what sent readers off to
        CourtListener before they ever saw our analysis."""
        body = render_litigation_body(_case(), event_type="complaint")
        assert "http" not in body
        # Naming CourtListener in the prose is fine (and tells the reader where the source lives) —
        # what must not be here is a clickable docket URL competing with the in-app CTA.
        assert "courtlistener.com" not in body.lower()

    def test_states_the_event_court_and_risk(self):
        body = render_litigation_body(
            _case(), event_type="order_on_motion", date_filed="2026-06-18",
            significance="critical", summary="Injunction denied.",
        )
        assert "Order On Motion" in body
        assert "NAW v. Maryland DoE" in body
        assert "MDD" in body
        assert "2026-06-18" in body
        assert "CRITICAL" in body
        assert "62/100" in body
        assert "Injunction denied." in body

    def test_injunction_leads_the_body_and_subject(self):
        # The one status that changes what a compliance team does tomorrow.
        case = _case(case_status="injunction_granted")
        assert render_litigation_body(case, event_type="order").startswith("ENFORCEMENT STAYED")
        assert "ENFORCEMENT STAYED" in render_litigation_subject(case, "critical")

    def test_subject_names_the_case(self):
        assert "NAW v. Maryland DoE" in render_litigation_subject(_case(), "notable")


class TestMastheadAndPreheader:
    """The masthead kicker used to read "SUPERFUN STUDIO · PRESENTS" — publisher ego in the most
    expensive real estate we own, and (because it sat first in the body) the inbox preview snippet
    as well."""

    def test_shell_has_no_studio_attribution_anywhere(self):
        html = build_text_alert_html("body", kicker="LITIGATION ALERT · 18 JUNE 2026")
        assert "SUPERFUN" not in html.upper()

    def test_kicker_is_the_edition_line(self):
        assert render_litigation_kicker(date(2026, 6, 18)) == "LITIGATION ALERT · 18 JUNE 2026"

    def test_kicker_survives_a_missing_date(self):
        assert render_litigation_kicker(None) == "LITIGATION ALERT"

    def test_no_kicker_means_no_empty_rule(self):
        """Omitting the line entirely beats rendering an empty bordered strip."""
        assert "letter-spacing:0.18em" not in build_text_alert_html("body")

    def test_preheader_leads_the_body_and_says_what_happened(self):
        pre = render_litigation_preheader(_case(), "injunction_motion", "critical")
        html = build_text_alert_html("body", preheader=pre)
        # Must precede the masthead — clients read forward from the top of <body>.
        assert html.index(pre) < html.index("Atlas Circular")
        assert "display:none" in html
        assert len(pre) < 100  # clients truncate past ~90 chars

    def test_preheader_leads_with_jurisdiction_then_the_stay(self):
        """Subscribers filter by state, so the jurisdiction is what marks the alert as theirs; a stay
        is the one outcome that outranks everything else after that."""
        pre = render_litigation_preheader(
            _case(case_status="injunction_granted", related_state="CO"), "order", "high"
        )
        assert pre.startswith("CO EPR")
        assert "enforcement is stayed" in pre


class TestFooterActions:
    def test_unsubscribe_is_a_real_button(self):
        html = build_text_alert_html("body", unsubscribe_url="https://api.test/unsub?token=x")
        assert 'href="https://api.test/unsub?token=x"' in html
        assert "Unsubscribe from these alerts" in html

    def test_forwarded_reader_can_subscribe(self):
        html = build_text_alert_html("body", subscribe_url="https://www.atlascircular.com/?utm_x=1")
        assert "Was this forwarded to you?" in html

    def test_neither_renders_when_not_passed(self):
        html = build_text_alert_html("body")
        assert "Unsubscribe" not in html
        assert "forwarded" not in html


class TestAtlasFirstLinking:
    def test_case_url_points_at_the_federal_page_deep_link(self):
        assert litigation_case_url(77).startswith(
            "https://www.atlascircular.com/federal?case=77&utm_source=atlas_alert"
        )

    def test_links_are_utm_tagged_for_ga4(self):
        """SendGrid click tracking is off (broken cert on the branded host), so UTM params are how a
        click becomes attributable."""
        url = litigation_case_url(77)
        assert "utm_medium=email" in url
        assert "utm_campaign=litigation_alert" in url
        assert "utm_medium=slack" in litigation_case_url(77, medium="slack")

    def test_utm_respects_an_existing_query_string(self):
        assert with_utm("https://x.test/a?b=1", "c").count("?") == 1
        assert with_utm("https://x.test/a", "c").count("?") == 1

    def test_bill_alert_litigation_block_links_in_app_not_to_courtlistener(self):
        """_get_litigation_context builds this block with a bare URL (Slack shares it); the email
        renderer has to turn it into a working anchor."""
        bill = types.SimpleNamespace(
            id=5, state="MD", bill_number="HB 234", title="Packaging EPR", status="enacted",
            material_categories=["packaging"], confidence_score=0.9, ai_summary=None,
            source_url="https://legiscan.com/MD/bill/HB234",
        )
        context = f"⚖️ Active Federal Litigation:\n• NAW v. MDE [MDD]\n  {litigation_case_url(77)}"
        html = _bill_block(bill, [], litigation_context=context)
        assert f'<a href="{litigation_case_url(77)}"' in html
        assert "courtlistener" not in html.lower()


class TestLinkify:
    def test_wraps_a_bare_url(self):
        assert _linkify("see https://x.test/a") .startswith("see <a href=\"https://x.test/a\"")

    def test_leaves_an_existing_anchor_alone(self):
        """Double-wrapping would emit href="<a href=…" and break the link."""
        html = '<a href="https://x.test/a">x</a>'
        assert _linkify(html) == html


class TestReplyTo:
    """Four templates end with "or reply to this email" — including the cancellation email, which
    asks for churn feedback. Without a Reply-To those replies go to the send-only alerts@ identity."""

    def test_replies_route_to_the_monitored_mailbox(self, monkeypatch):
        monkeypatch.setattr(settings, "sendgrid_reply_to", "kenny@atlascircular.com")
        message = Mail(
            from_email="alerts@atlascircular.com", to_emails="a@example.com",
            subject="s", plain_text_content="t", html_content="<p>t</p>",
        )
        _apply_reply_to(message)
        assert message.get()["reply_to"] == {"email": "kenny@atlascircular.com"}

    def test_unconfigured_sends_exactly_as_before(self, monkeypatch):
        monkeypatch.setattr(settings, "sendgrid_reply_to", "")
        message = Mail(
            from_email="alerts@atlascircular.com", to_emails="a@example.com",
            subject="s", plain_text_content="t", html_content="<p>t</p>",
        )
        _apply_reply_to(message)
        assert "reply_to" not in message.get()


class TestClickTracking:
    def test_disabled_by_default(self, monkeypatch):
        """SendGrid's rewrite sends every link through url7082.atlascircular.com, whose certificate
        doesn't cover it — so every link in every email dead-ends on a browser security warning."""
        monkeypatch.setattr(settings, "sendgrid_click_tracking", False)
        message = types.SimpleNamespace()
        _apply_tracking(message)
        assert message.tracking_settings.click_tracking.enable is False
        assert message.tracking_settings.click_tracking.enable_text is False

    def test_left_untouched_when_re_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "sendgrid_click_tracking", True)
        message = types.SimpleNamespace()
        _apply_tracking(message)
        assert not hasattr(message, "tracking_settings")
