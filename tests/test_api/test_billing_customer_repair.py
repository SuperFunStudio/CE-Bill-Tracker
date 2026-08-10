"""A stored Stripe customer id can go dead — a test-mode `cus_…` left on the row after the deploy
moved to live keys, or a customer deleted in the dashboard. That surfaced as a 500 on "Manage plan".
These cover the detector and the repair: adopt an existing customer for the email when there is one
(so a real subscription stays attached to the seat), mint a new one only when there isn't."""
import pytest
import stripe

from app.api import billing


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class _User:
    email = "member@example.com"
    uid = "firebase-uid-1"


class _Ent:
    def __init__(self, customer_id=None):
        self.stripe_customer_id = customer_id


class _Obj:
    """Stand-in for a StripeObject — attribute access, as the SDK returns."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_detects_missing_customer():
    err = stripe.InvalidRequestError("No such customer: 'cus_dead'", param="customer")
    assert billing._is_missing_customer(err)


@pytest.mark.parametrize(
    "err",
    [
        stripe.InvalidRequestError("No such price: 'price_x'", param="price"),
        ValueError("No such customer: 'cus_dead'"),  # right text, wrong class — not Stripe's verdict
    ],
)
def test_other_errors_are_not_a_missing_customer(err):
    assert not billing._is_missing_customer(err)


@pytest.mark.asyncio
async def test_repair_adopts_the_existing_customer_for_the_email(monkeypatch):
    monkeypatch.setattr(
        stripe.Customer, "list", lambda **kw: _Obj(data=[_Obj(id="cus_live")]), raising=False
    )
    monkeypatch.setattr(
        stripe.Customer,
        "create",
        lambda **kw: pytest.fail("should adopt the existing customer, not mint a new one"),
        raising=False,
    )
    db, ent = _FakeDB(), _Ent("cus_dead")

    got = await billing._repair_customer(db, ent, _User())

    assert got == "cus_live"
    assert ent.stripe_customer_id == "cus_live"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_repair_creates_a_customer_when_the_email_has_none(monkeypatch):
    monkeypatch.setattr(stripe.Customer, "list", lambda **kw: _Obj(data=[]), raising=False)
    monkeypatch.setattr(stripe.Customer, "create", lambda **kw: _Obj(id="cus_new"), raising=False)
    db, ent = _FakeDB(), _Ent("cus_dead")

    assert await billing._repair_customer(db, ent, _User()) == "cus_new"
    assert ent.stripe_customer_id == "cus_new"


@pytest.mark.asyncio
async def test_ensure_customer_repairs_a_dead_id(monkeypatch):
    def _retrieve(cid, **kw):
        raise stripe.InvalidRequestError(f"No such customer: '{cid}'", param="customer")

    monkeypatch.setattr(stripe.Customer, "retrieve", _retrieve, raising=False)
    monkeypatch.setattr(
        stripe.Customer, "list", lambda **kw: _Obj(data=[_Obj(id="cus_live")]), raising=False
    )
    ent = _Ent("cus_dead")

    await billing._ensure_customer(_FakeDB(), ent, _User())

    assert ent.stripe_customer_id == "cus_live"


@pytest.mark.asyncio
async def test_ensure_customer_keeps_a_live_id_untouched(monkeypatch):
    monkeypatch.setattr(
        stripe.Customer, "retrieve", lambda cid, **kw: _Obj(id=cid), raising=False
    )
    monkeypatch.setattr(
        stripe.Customer, "list", lambda **kw: pytest.fail("no repair needed"), raising=False
    )
    ent = _Ent("cus_good")

    await billing._ensure_customer(_FakeDB(), ent, _User())

    assert ent.stripe_customer_id == "cus_good"
