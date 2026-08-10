"""The founding-seat counter is the one number on the pricing page a visitor watches, so what it
counts has to be exactly right.

The bug these pin: our own test accounts hold complimentary Pro so the paid product can be exercised
end-to-end, which made them indistinguishable from a real comped grant. Four of them were consuming
founding seats — the live page said 40 of 50 remaining when the true figure was 44.
"""
import pytest
from sqlalchemy.dialects import postgresql

from app.api import billing
from app.config import settings


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _CapturingDB:
    """Records the statement the endpoint runs and returns a canned count."""

    def __init__(self, count):
        self._count = count
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult(self._count)

    def compiled_sql(self) -> str:
        return str(self.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        ))


# The route is wrapped by slowapi's rate limiter, which insists on a real starlette Request. The
# limit isn't what's under test, so unwrap to the handler itself.
_founding_seats = billing.founding_seats.__wrapped__


async def _call(count):
    db = _CapturingDB(count)
    result = await _founding_seats(request=None, db=db)
    return result, db


@pytest.mark.asyncio
async def test_internal_accounts_are_excluded_from_the_count():
    _, db = await _call(0)
    sql = db.compiled_sql().lower()
    assert "not in" in sql
    for email in settings.internal_emails:
        assert email.lower() in sql


@pytest.mark.asyncio
async def test_reports_remaining_against_the_advertised_total():
    result, _ = await _call(6)
    assert result == {"total": 50, "claimed": 6, "remaining": 44}


@pytest.mark.asyncio
async def test_an_oversubscribed_window_never_renders_a_negative_remainder():
    result, _ = await _call(73)
    assert result["claimed"] == 50
    assert result["remaining"] == 0


@pytest.mark.asyncio
async def test_off_book_grants_still_consume_seats(monkeypatch):
    """The escape hatch for seats arranged off-platform — it must add, not decorate."""
    monkeypatch.setattr(billing, "_FOUNDING_SEATS_GRANTED_OFF_BOOK", 3)
    result, _ = await _call(6)
    assert result["claimed"] == 9


@pytest.mark.asyncio
async def test_comped_pro_still_counts(monkeypatch):
    """Excluding our own accounts must not become "comps don't count" — a real complimentary Pro seat
    consumes the founding allocation exactly like a paid one."""
    monkeypatch.setattr(settings, "internal_emails", [])
    _, db = await _call(0)
    sql = db.compiled_sql().lower()
    assert "comp" in sql and "'pro'" in sql
    assert "not in" not in sql
