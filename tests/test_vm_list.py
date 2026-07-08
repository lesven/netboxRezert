from tests.conftest import issue_token


def test_vm_list_shows_only_own_vms(client):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.get(f"/r/{token}")
    assert resp.status_code == 200
    assert "vm-erp-prod-01" in resp.text
    assert "vm-webshop-frontend" in resp.text
    # owned by a different contact -> must not show up
    assert "vm-reporting-01" not in resp.text


def test_vm_list_empty_for_contact_without_vms(client):
    token = issue_token(7, "David Fischer")
    resp = client.get(f"/r/{token}")
    assert resp.status_code == 200
    assert "keine VMs" in resp.text
