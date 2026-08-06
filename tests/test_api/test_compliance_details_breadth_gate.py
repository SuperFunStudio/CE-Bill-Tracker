"""Pins the paywall boundary for compliance_details: gated on BREADTH, not depth.

One bill's extraction is free (it's a reading of statute text we serve free at /bills/{id}/text and
publish as HTML at /bill/{id}/{slug}). The corpus-wide views are what's sold. These tests hold the
line that actually matters — that the BULK list schema can never carry the extraction — so a future
"just add compliance_details to BillSummary for convenience" gets caught here rather than in prod.

See docs/SECURITY_ASSESSMENT.md C-1 and the 2026-08-06 scope note.
"""
import inspect

from app.api.bills import get_bill
from app.schemas import BillDetail, BillSummary


def test_bulk_list_schema_never_carries_the_extraction():
    # The one-call harvest that C-1 closed. BillSummary is what GET /bills returns, per row.
    assert "compliance_details" not in BillSummary.model_fields


def test_per_bill_detail_schema_carries_it():
    assert "compliance_details" in BillDetail.model_fields


def test_per_bill_detail_is_not_entitlement_gated():
    # The endpoint takes no auth dependency at all — a Pro check here would silently re-gate the
    # record and empty out the public bill pages, which are built anonymously.
    params = inspect.signature(get_bill).parameters
    assert "is_pro" not in params
    assert set(params) == {"bill_id", "db"}
