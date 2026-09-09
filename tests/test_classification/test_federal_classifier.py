"""Parser-level guards on FederalClassifier.

friction_type was the one classifier axis with no validation. Adding "waste_shipment" to
instrument_type made Haiku echo it into friction_type too, and an unvalidated value flows
straight to the /federal page's FrictionBadge and the API's friction_type filter facet. These
tests pin the coercion rules for all three axes without spending an API call.
"""
import json
from types import SimpleNamespace

import pytest

from app.classification.federal_classifier import (
    _VALID_FRICTION,
    _VALID_INSTRUMENTS,
    FederalClassifier,
)


class _StubClient:
    """Stands in for anthropic.AsyncAnthropic; replays one canned JSON body."""

    def __init__(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.messages = SimpleNamespace(
            create=lambda **kw: _resolved(
                SimpleNamespace(content=[SimpleNamespace(text=text)])
            )
        )


async def _resolved(value):
    return value


async def _classify(payload):
    return await FederalClassifier(client=_StubClient(payload)).classify(title="t")


def test_waste_shipment_is_a_valid_instrument():
    """The federal vocabulary tracks the bill classifier's transboundary instrument."""
    assert "waste_shipment" in _VALID_INSTRUMENTS


@pytest.mark.asyncio
async def test_instrument_name_leaked_into_friction_is_coerced():
    """The observed failure: Haiku answered friction_type="waste_shipment"."""
    r = await _classify({
        "is_relevant": True, "confidence": 0.92, "preemption_risk": "low",
        "friction_type": "waste_shipment", "instrument_type": "waste_shipment",
    })
    assert r.friction_type == "compliance_burden"
    assert r.instrument_type == "waste_shipment"
    assert r.in_scope is True


@pytest.mark.asyncio
async def test_valid_friction_is_passed_through():
    r = await _classify({
        "is_relevant": True, "confidence": 0.9, "preemption_risk": "low",
        "friction_type": "comment_opportunity", "instrument_type": "epr",
    })
    assert r.friction_type == "comment_opportunity"


@pytest.mark.asyncio
async def test_irrelevant_action_has_no_friction_and_no_risk():
    """Irrelevant => no friction, even when the model claims otherwise."""
    r = await _classify({
        "is_relevant": False, "confidence": 0.95, "preemption_risk": "high",
        "friction_type": "preemption", "instrument_type": "waste_shipment",
    })
    assert (r.preemption_risk, r.friction_type) == ("none", "none")
    assert r.in_scope is False


@pytest.mark.asyncio
async def test_unknown_instrument_and_risk_fall_back():
    r = await _classify({
        "is_relevant": True, "confidence": 0.8, "preemption_risk": "catastrophic",
        "friction_type": "vibes", "instrument_type": "space_elevator",
    })
    assert r.preemption_risk == "none"
    assert r.instrument_type == "other"
    assert r.friction_type in _VALID_FRICTION


@pytest.mark.asyncio
async def test_confidence_floor_gates_in_scope():
    """A low-confidence is_relevant guess does not count as relevant."""
    r = await _classify({
        "is_relevant": True, "confidence": 0.3, "preemption_risk": "low",
        "friction_type": "study", "instrument_type": "epr",
    })
    assert r.is_relevant is True and r.in_scope is False


@pytest.mark.asyncio
async def test_json_in_markdown_fence_still_parses():
    """Haiku wraps its answer in ```json fences in practice."""
    r = await _classify(
        '```json\n{"is_relevant": true, "confidence": 0.9, "preemption_risk": "low",'
        ' "friction_type": "compliance_burden", "instrument_type": "waste_shipment"}\n```'
    )
    assert r.in_scope is True and r.instrument_type == "waste_shipment"
