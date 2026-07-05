"""Tests for GET /compliance/fee-schedule — pure in-code reference data, no DB.

The endpoint is mounted on a minimal FastAPI app so no database/scheduler is touched.
Expected numbers come straight from app/scoring/ca_sb54_fees.py (the source of truth).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.compliance import router
from app.scoring.ca_sb54_fees import LB_PER_TONNE

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _get_schedule():
    resp = client.get("/compliance/fee-schedule")
    assert resp.status_code == 200
    return resp.json()


def _category(data, name):
    return next(c for c in data["categories"] if c["material_category"] == name)


def _rate(cat, tier):
    return next(r for r in cat["rates"] if r["tier"] == tier)


def test_fee_schedule_returns_200_with_metadata():
    data = _get_schedule()
    assert data["program"] == "CA SB-54"
    assert "Ch. 9 Table 5" in data["basis"]
    assert data["rates_final_expected"] == "October 2026"
    assert data["lb_per_tonne"] == LB_PER_TONNE
    # All five coarse material categories are present.
    cats = {c["material_category"] for c in data["categories"]}
    assert cats == {
        "plastic_packaging", "plastic_film", "paper_packaging",
        "glass_packaging", "aluminum_packaging",
    }


def test_known_rate_spot_check_glass():
    """Glass bottles & jars: 1¢/lb, no adder → $22/tonne (lowest fee in the schedule)."""
    glass = _category(_get_schedule(), "glass_packaging")
    best = _rate(glass, "best")
    assert best["format_name"] == "Glass bottles & jars"
    assert best["base_cents_per_lb"] == 1.0
    assert best["plastic_adder_cents_per_lb"] == 0.0
    assert best["total_cents_per_lb"] == 1.0
    assert best["usd_per_tonne"] == round(1.0 / 100 * LB_PER_TONNE)  # 22
    assert not glass["includes_plastic_adder"]
    assert "glass" in glass["aliases"]


def test_plastic_adder_exposed_and_applied():
    """Plastic CMCs carry the 21¢/lb Reuse (4) + PPMF (17) adder, exposed as its own field."""
    data = _get_schedule()
    assert data["plastic_adder"]["reuse_cents_per_lb"] == 4.0
    assert data["plastic_adder"]["ppmf_cents_per_lb"] == 17.0
    assert data["plastic_adder"]["total_cents_per_lb"] == 21.0

    plastic = _category(data, "plastic_packaging")
    assert plastic["includes_plastic_adder"]
    best = _rate(plastic, "best")
    # PET/HDPE clear bottle: 29¢ base + 21¢ adder = 50¢/lb → $1102/tonne.
    assert best["base_cents_per_lb"] == 29.0
    assert best["plastic_adder_cents_per_lb"] == 21.0
    assert best["total_cents_per_lb"] == 50.0
    assert best["usd_per_tonne"] == round(50.0 / 100 * LB_PER_TONNE)  # 1102

    # Non-plastic categories never carry the adder.
    for name in ("paper_packaging", "glass_packaging", "aluminum_packaging"):
        cat = _category(data, name)
        assert all(r["plastic_adder_cents_per_lb"] == 0.0 for r in cat["rates"])


def test_representative_tier_carries_high_scenario():
    plastic = _category(_get_schedule(), "plastic_packaging")
    rep = _rate(plastic, "representative")
    assert rep["format_name"] is None
    # 33¢ base + 21¢ adder = 54¢/lb → $1190/tonne; high scenario ≈ 2.5x.
    assert rep["usd_per_tonne"] == round(54.0 / 100 * LB_PER_TONNE)
    assert rep["usd_per_tonne_high"] == round(rep["usd_per_tonne"] * 2.5)
    # best/worst tiers don't publish a high scenario.
    assert _rate(plastic, "best")["usd_per_tonne_high"] is None
