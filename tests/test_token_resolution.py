from app import db
from tests.conftest import issue_token


def test_unknown_token_resolves_to_none(settings):
    assert db.resolve_token("does-not-exist") is None


def test_stored_token_resolves_to_contact(settings):
    token = issue_token(1, "Michael Brandt")
    assert db.resolve_token(token) == 1


def test_invalid_token_returns_404_page(client):
    resp = client.get("/r/unbekannter-token")
    assert resp.status_code == 404
    assert "ungültig" in resp.text.lower() or "unbekannt" in resp.text.lower()
