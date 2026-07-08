import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.netbox_client import get_netbox_client


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "tokens.sqlite3"))
    monkeypatch.setenv("NETBOX_MOCK", "true")
    monkeypatch.setenv("BASE_URL", "http://tool.internal")
    get_settings.cache_clear()
    get_netbox_client.cache_clear()
    db.init_db()
    yield get_settings()
    get_settings.cache_clear()
    get_netbox_client.cache_clear()


@pytest.fixture()
def client(settings):
    db.init_db()
    with TestClient(app=_make_app()) as c:
        yield c


def _make_app():
    # Imported lazily so the settings/env patches above are applied first.
    from app.main import app

    return app


@pytest.fixture()
def netbox(settings):
    return get_netbox_client()


def issue_token(contact_id: int, contact_name: str) -> str:
    import uuid

    token = uuid.uuid4().hex
    db.store_token(token, contact_id, contact_name)
    return token
