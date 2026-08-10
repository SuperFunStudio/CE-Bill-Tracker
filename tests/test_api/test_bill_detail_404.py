"""Pins GET /bills/{id} on an unknown id: 404, not 500.

This shipped as a 500 because get_bill used `.one()`, which raises NoResultFound on an empty result.
The developer-docs quickstart curled a placeholder id, so the first request a new API user copied out
of our own documentation returned "Internal server error" — reading as a broken API rather than a bad
id. Stubbed session, no DB: the point is the miss path, not the query.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bills import router
from app.database import get_db


class _EmptyResult:
    def one_or_none(self):
        return None


class _MissSession:
    """Every query finds nothing — the unknown-bill case."""

    async def execute(self, *_args, **_kwargs):
        return _EmptyResult()


app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_db] = lambda: _MissSession()
client = TestClient(app)


def test_unknown_bill_id_is_404_not_500():
    resp = client.get("/bills/12345")
    assert resp.status_code == 404


def test_404_body_names_the_id_it_could_not_find():
    # The whole failure mode was an opaque error, so the id has to make it into the message.
    assert "12345" in client.get("/bills/12345").json()["detail"]
