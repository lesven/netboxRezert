import pytest

from app.netbox_client import NetboxError
from app.netbox_mock import MockNetboxClient


@pytest.fixture()
def mock_client():
    return MockNetboxClient()


def test_get_contact_returns_known_contact(mock_client):
    contact = mock_client.get_contact(2)
    assert contact is not None
    assert contact.name == "Anna Schmidt"


def test_get_contact_returns_none_for_unknown_id(mock_client):
    assert mock_client.get_contact(999) is None


def test_search_contacts_is_case_insensitive_substring_match(mock_client):
    results = mock_client.search_contacts("schmidt", limit=10)
    assert [c.name for c in results] == ["Anna Schmidt"]

    results = mock_client.search_contacts("ANNA", limit=10)
    assert [c.name for c in results] == ["Anna Schmidt"]


def test_search_contacts_respects_limit(mock_client):
    results = mock_client.search_contacts("a", limit=2)  # matches several contacts
    assert len(results) == 2


def test_search_contacts_no_match_returns_empty_list(mock_client):
    assert mock_client.search_contacts("does-not-exist", limit=10) == []


def test_get_vm_returns_known_vm_with_resolved_owner_name(mock_client):
    vm = mock_client.get_vm(101)
    assert vm is not None
    assert vm.owner_contact_id == 1
    assert vm.owner_contact_name == "Michael Brandt (Bereichsleiter IT)"


def test_get_vm_returns_none_for_unknown_id(mock_client):
    assert mock_client.get_vm(999) is None


def test_list_vms_by_owner_filters_correctly(mock_client):
    vms = mock_client.list_vms_by_owner(2)
    assert [vm.id for vm in vms] == [106]


def test_list_vms_by_owner_empty_for_contact_without_vms(mock_client):
    assert mock_client.list_vms_by_owner(7) == []


def test_list_vms_with_owner_excludes_vms_with_no_owner(mock_client):
    mock_client._vms[106]["owner"] = None
    ids = {vm.id for vm in mock_client.list_vms_with_owner()}
    assert 106 not in ids
    assert 101 in ids


def test_update_vm_owner_changes_owner(mock_client):
    mock_client.update_vm_owner(101, 3)
    assert mock_client.get_vm(101).owner_contact_id == 3


def test_update_vm_owner_raises_for_unknown_vm(mock_client):
    with pytest.raises(NetboxError):
        mock_client.update_vm_owner(999, 3)


def test_update_vm_owner_raises_for_unknown_contact(mock_client):
    with pytest.raises(NetboxError):
        mock_client.update_vm_owner(101, 999)


def test_create_journal_entry_is_recorded(mock_client):
    mock_client.create_journal_entry(101, "some comment")
    assert mock_client._journal == [(101, "some comment")]


def test_update_vm_recertification_sets_fields(mock_client):
    mock_client.update_vm_recertification(101, True, "läuft", "2026-07-08T10:00:00+00:00")
    vm = mock_client.get_vm(101)
    assert vm.still_in_use is True
    assert vm.comment == "läuft"
    assert vm.rezert_date == "2026-07-08T10:00:00+00:00"


def test_update_vm_recertification_raises_for_unknown_vm(mock_client):
    with pytest.raises(NetboxError):
        mock_client.update_vm_recertification(999, True, "x", "2026-07-08T10:00:00+00:00")


def test_clients_are_independent_instances(mock_client):
    # each MockNetboxClient() must start from a fresh copy of the fixtures,
    # not share mutable state across instances (e.g. via a shared module dict)
    mock_client.update_vm_owner(101, 3)
    other = MockNetboxClient()
    assert other.get_vm(101).owner_contact_id == 1
