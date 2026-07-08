from app.netbox_client import NetboxClient, NetboxError
from app.schemas import Contact, Vm
from tests.conftest import issue_token


def test_confirm_filters_unchanged_rows(client):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(
        f"/r/{token}/confirm",
        data={"owner_101": "2", "owner_102": "1"},  # 102 unchanged (still owner 1)
    )
    assert resp.status_code == 200
    assert "vm-erp-prod-01" in resp.text
    assert "Anna Schmidt" in resp.text
    assert "vm-erp-prod-02" not in resp.text  # unchanged VM must not appear in the diff


def test_confirm_lists_every_vm_in_a_multi_vm_bulk_change(client):
    # Simulates the multi-select "assign several VMs to one new owner at
    # once" flow: several rows changed to the same target contact in a
    # single round-trip must all show up individually in the diff, not be
    # collapsed into a summary line.
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(
        f"/r/{token}/confirm",
        data={"owner_101": "3", "owner_102": "3", "owner_103": "3"},
    )
    assert resp.status_code == 200
    assert "vm-erp-prod-01" in resp.text
    assert "vm-erp-prod-02" in resp.text
    assert "vm-fileserver-03" in resp.text
    # one visible diff row per changed VM (not collapsed into a summary line)
    assert resp.text.count("&rarr;") == 3


def test_save_reassigns_multiple_vms_to_one_owner_in_one_request(client, netbox):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(
        f"/r/{token}/save",
        data={
            "vm_id": ["101", "102", "103"],
            "vm_name": ["vm-erp-prod-01", "vm-erp-prod-02", "vm-fileserver-03"],
            "old_contact_id": ["1", "1", "1"],
            "old_contact_name": ["Michael Brandt", "Michael Brandt", "Michael Brandt"],
            "new_contact_id": ["3", "3", "3"],
            "new_contact_name": ["Tobias Weber", "Tobias Weber", "Tobias Weber"],
        },
    )
    assert resp.status_code == 200
    assert resp.text.count("✅") == 3
    for vm_id in (101, 102, 103):
        assert netbox.get_vm(vm_id).owner_contact_id == 3
    assert len(netbox._journal) == 3


def test_confirm_with_no_changes_returns_to_list(client):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(f"/r/{token}/confirm", data={"owner_101": "1"})
    assert resp.status_code == 200
    assert "Keine Änderungen" in resp.text


def test_save_updates_owner_and_writes_journal(client, netbox):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(
        f"/r/{token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt (Bereichsleiter IT)"],
            "new_contact_id": ["2"],
            "new_contact_name": ["Anna Schmidt"],
        },
    )
    assert resp.status_code == 200
    assert "✅" in resp.text
    assert "vm-erp-prod-01" in resp.text

    updated_vm = netbox.get_vm(101)
    assert updated_vm.owner_contact_id == 2
    assert netbox._journal, "journal entry was not recorded"
    vm_id, comment = netbox._journal[-1]
    assert vm_id == 101
    assert "Michael Brandt" in comment
    assert "Anna Schmidt" in comment
    assert "Rezertifizierungstool" in comment


class _FailingClient(NetboxClient):
    def get_contact(self, contact_id):
        return Contact(id=contact_id, name=f"Contact {contact_id}")

    def search_contacts(self, query, limit):
        return []

    def list_vms_by_owner(self, contact_id):
        return []

    def get_vm(self, vm_id):
        return Vm(
            id=vm_id, name="vm-x", owner_contact_id=1, owner_contact_name="A",
            vcpus=1, memory_gb=1, disk_gb=1,
        )

    def list_vms_with_owner(self):
        return []

    def update_vm_owner(self, vm_id, new_contact_id):
        raise NetboxError("NetBox ist nicht erreichbar")

    def create_journal_entry(self, vm_id, comment):
        raise NetboxError("sollte nie aufgerufen werden")

    def update_vm_recertification(self, vm_id, still_in_use, comment, rezert_date):
        raise NetboxError("sollte nie aufgerufen werden")


def test_save_surfaces_netbox_write_errors(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _FailingClient())
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
    assert resp.status_code == 200
    assert "❌" in resp.text
    assert "nicht erreichbar" in resp.text


class _JournalFailingClient(_FailingClient):
    def update_vm_owner(self, vm_id, new_contact_id):
        return None

    def create_journal_entry(self, vm_id, comment):
        raise NetboxError("Journal-Endpoint down")


def test_save_warns_when_journal_entry_fails_but_owner_was_updated(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _JournalFailingClient())
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
    assert resp.status_code == 200
    assert "✅" in resp.text  # owner change itself succeeded
    assert "Audit-Journal-Eintrag konnte nicht geschrieben werden" in resp.text
