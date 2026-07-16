"""Error-path integration tests: NetBox outages and invalid tokens must
always surface as a user-visible error page/JSON, never a 500 or silence.
"""

from app.netbox_client import NetboxError, get_netbox_client
from tests.conftest import issue_token
from tests.test_confirm_and_save import _FailingClient


class _ListFailingClient(_FailingClient):
    def list_vms_by_owner(self, contact_id):
        raise NetboxError("NetBox antwortet nicht")


class _SearchFailingClient(_FailingClient):
    def search_contacts(self, query, limit):
        raise NetboxError("NetBox antwortet nicht")


class _GetVmFailingClient(_FailingClient):
    def get_vm(self, vm_id):
        raise NetboxError("NetBox antwortet nicht")


class _GetContactFailingClient(_FailingClient):
    def get_contact(self, contact_id):
        raise NetboxError("interner-hostname.example.internal antwortet nicht")


def test_vm_list_shows_502_error_page_with_retry_link_when_netbox_down(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _ListFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}")
    assert resp.status_code == 502
    assert "NetBox nicht erreichbar" in resp.text
    assert f"/r/{token}" in resp.text  # retry link back to the list


def test_contact_search_returns_502_json_when_netbox_down(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _SearchFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}/contacts/search", params={"q": "anna"})
    assert resp.status_code == 502
    assert "error" in resp.json()


def test_confirm_shows_502_error_page_when_vm_recheck_fails(client, monkeypatch):
    # /confirm re-fetches every VM fresh from NetBox; if that fails, the whole
    # confirmation must abort visibly instead of showing a partial diff.
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _GetVmFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/confirm", data={"owner_101": "2"})
    assert resp.status_code == 502
    assert "NetBox nicht erreichbar" in resp.text


def test_vm_list_error_page_does_not_leak_netbox_internals(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _ListFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}")
    assert resp.status_code == 502
    assert "NetBox antwortet nicht" not in resp.text


def test_contact_search_error_does_not_leak_netbox_internals(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _SearchFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}/contacts/search", params={"q": "anna"})
    assert resp.status_code == 502
    assert "NetBox antwortet nicht" not in resp.json()["error"]


def test_confirm_error_page_does_not_leak_netbox_internals(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _GetVmFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/confirm", data={"owner_101": "2"})
    assert resp.status_code == 502
    assert "NetBox antwortet nicht" not in resp.text


def test_confirm_skips_non_numeric_vm_id_key_instead_of_500(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/confirm", data={"owner_abc": "1"})
    assert resp.status_code == 200
    assert "Keine Änderungen" in resp.text


def test_confirm_skips_non_numeric_contact_value_instead_of_500(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/confirm", data={"owner_101": "xyz"})
    assert resp.status_code == 200
    assert "Keine Änderungen" in resp.text


def test_recertify_skips_non_numeric_vm_id_key_instead_of_500(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={"recert_xyz": "ja"})
    assert resp.status_code == 200
    assert "Keine Rezertifizierung" in resp.text


def test_confirm_no_op_branch_shows_502_when_netbox_down(client, monkeypatch):
    # empty/no-op submission renders the VM list again via _render_vm_list,
    # which itself calls NetBox - that call-site was previously unguarded.
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _GetContactFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/confirm", data={"owner_101": "1"})  # unchanged -> no-op
    assert resp.status_code == 502
    assert "interner-hostname.example.internal" not in resp.text


def test_recertify_no_op_branch_shows_502_when_netbox_down(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _GetContactFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={})
    assert resp.status_code == 502
    assert "interner-hostname.example.internal" not in resp.text


def test_save_shows_502_when_requester_lookup_fails(client, netbox, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _GetContactFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt"],
            "new_contact_id": ["2"],
            "new_contact_name": ["Anna Schmidt"],
        },
    )
    assert resp.status_code == 502
    assert "interner-hostname.example.internal" not in resp.text


def test_save_skips_non_numeric_old_contact_id_instead_of_500(client, netbox):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["abc"],
            "old_contact_name": [""],
            "new_contact_id": ["2"],
            "new_contact_name": ["Anna Schmidt"],
        },
    )
    assert resp.status_code == 200
    assert "✅" in resp.text
    assert netbox.get_vm(101).owner_contact_id == 2


def test_confirm_ignores_unrelated_form_fields(client):
    # the list page posts recert_*/comment_* fields from the second form's
    # namespace; /confirm must only ever interpret owner_* keys
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/confirm",
        data={"owner_101": "2", "recert_101": "nein", "comment_101": "ignore me"},
    )
    assert resp.status_code == 200
    assert "vm-erp-prod-01" in resp.text
    assert resp.text.count("&rarr;") == 1  # exactly the one owner change, nothing else


def test_confirm_rejects_invalid_token(client):
    resp = client.post("/r/unbekannt/confirm", data={"owner_101": "2"})
    assert resp.status_code == 404


def test_save_rejects_invalid_token(client, netbox):
    resp = client.post(
        "/r/unbekannt/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt"],
            "new_contact_id": ["2"],
            "new_contact_name": ["Anna Schmidt"],
        },
    )
    assert resp.status_code == 404
    assert netbox.get_vm(101).owner_contact_id == 1  # nothing was written


def test_recertify_rejects_invalid_token(client, netbox):
    resp = client.post("/r/unbekannt/recertify", data={"recert_101": "ja"})
    assert resp.status_code == 404
    assert netbox.get_vm(101).still_in_use is None  # nothing was written


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_factory_returns_real_client_when_mock_disabled(settings, monkeypatch):
    from app.config import get_settings
    from app.netbox_real import RestNetboxClient

    monkeypatch.setenv("NETBOX_MOCK", "false")
    monkeypatch.setenv("NETBOX_URL", "http://netbox.test")
    monkeypatch.setenv("NETBOX_TOKEN", "dummy")
    get_settings.cache_clear()
    get_netbox_client.cache_clear()
    try:
        assert isinstance(get_netbox_client(), RestNetboxClient)
    finally:
        get_settings.cache_clear()
        get_netbox_client.cache_clear()
