"""Unit tests for RestNetboxClient against faked pynetbox records/endpoints.

No network involved: pynetbox.api() itself does no I/O on construction, and
the tests replace the endpoint objects with in-memory fakes. This pins down
the record→schema translation and the RequestError→NetboxError wrapping,
which is exactly the layer that has never run against a real instance yet.
"""

from types import SimpleNamespace

import pytest
from pynetbox.core.query import RequestError

from app.netbox_client import NetboxError
from app.netbox_real import (
    COMMENT_FIELD,
    OWNER_FIELD,
    REZERT_DATE_FIELD,
    STILL_IN_USE_FIELD,
    RestNetboxClient,
)


class _FakeResponse:
    """Just enough of a requests.Response for RequestError.__init__."""

    def __init__(self, status_code=500, url="http://netbox.test/api/", reason="Server Error"):
        self.status_code = status_code
        self.url = url
        self.reason = reason
        self.text = "kaputt"
        self.request = SimpleNamespace(body=None)

    def json(self):
        return {"detail": "kaputt"}


def _request_error(status_code=500) -> RequestError:
    return RequestError(_FakeResponse(status_code=status_code))


class FakeVmRecord:
    def __init__(
        self,
        id=101,
        name="vm-x",
        custom_fields=None,
        vcpus=2,
        memory=4096,
        disk=100,
        save_ok=True,
    ):
        self.id = id
        self.name = name
        self.custom_fields = {} if custom_fields is None else custom_fields
        self.vcpus = vcpus
        self.memory = memory
        self.disk = disk
        self._save_ok = save_ok
        self.saved = False

    def save(self):
        self.saved = True
        return self._save_ok


def _contact_record(id=1, display="Anna Schmidt", name="anna-schmidt", email="a.schmidt@example.com"):
    return SimpleNamespace(id=id, display=display, name=name, email=email)


class FakeEndpoint:
    """Records calls; each behavior (get/filter/all/create) is configurable."""

    def __init__(self, get_result=None, filter_result=(), all_result=(), raise_error=False):
        self._get_result = get_result
        self._filter_result = list(filter_result)
        self._all_result = list(all_result)
        self._raise = raise_error
        self.calls: list[tuple] = []

    def _maybe_raise(self):
        if self._raise:
            raise _request_error()

    def get(self, *args, **kwargs):
        self.calls.append(("get", args, kwargs))
        self._maybe_raise()
        return self._get_result

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        self._maybe_raise()
        return iter(self._filter_result)

    def all(self):
        self.calls.append(("all", (), {}))
        self._maybe_raise()
        return iter(self._all_result)

    def create(self, *args, **kwargs):
        self.calls.append(("create", args, kwargs))
        self._maybe_raise()
        return SimpleNamespace(id=1)


def _client(
    contacts: FakeEndpoint | None = None,
    vms: FakeEndpoint | None = None,
    journal: FakeEndpoint | None = None,
) -> RestNetboxClient:
    client = RestNetboxClient(url="http://netbox.test/", token="dummy")
    client._api = SimpleNamespace(
        tenancy=SimpleNamespace(contacts=contacts or FakeEndpoint()),
        virtualization=SimpleNamespace(virtual_machines=vms or FakeEndpoint()),
        extras=SimpleNamespace(journal_entries=journal or FakeEndpoint()),
    )
    return client


# --- record -> schema translation -------------------------------------------


def test_to_vm_unwraps_nested_owner_object_and_converts_units():
    record = FakeVmRecord(
        id=101,
        name="vm-erp-prod-01",
        custom_fields={OWNER_FIELD: {"id": 3, "display": "Tobias Weber", "url": "..."}},
        vcpus=8,
        memory=32768,  # NetBox stores MB
        disk=500,
    )
    vm = _client()._to_vm(record)
    assert vm.owner_contact_id == 3
    assert vm.owner_contact_name == "Tobias Weber"
    assert vm.vcpus == 8.0
    assert vm.memory_gb == 32.0  # MB -> GB
    assert vm.disk_gb == 500.0
    # trailing slash of the base URL must not double up
    assert vm.netbox_url == "http://netbox.test/virtualization/virtual-machines/101/"


def test_to_vm_handles_missing_owner_and_missing_metrics():
    record = FakeVmRecord(custom_fields={}, vcpus=None, memory=None, disk=None)
    vm = _client()._to_vm(record)
    assert vm.owner_contact_id is None
    assert vm.owner_contact_name is None
    assert vm.vcpus is None
    assert vm.memory_gb is None
    assert vm.disk_gb is None


def test_to_vm_handles_owner_field_explicitly_null():
    # NetBox returns the custom field key with value None when unset
    record = FakeVmRecord(custom_fields={OWNER_FIELD: None})
    vm = _client()._to_vm(record)
    assert vm.owner_contact_id is None


def test_to_vm_passes_recert_fields_through_as_plain_scalars():
    record = FakeVmRecord(
        custom_fields={
            STILL_IN_USE_FIELD: True,
            COMMENT_FIELD: "läuft weiter",
            REZERT_DATE_FIELD: "2026-07-08T10:31:31+00:00",
        }
    )
    vm = _client()._to_vm(record)
    assert vm.still_in_use is True
    assert vm.comment == "läuft weiter"
    assert vm.rezert_date == "2026-07-08T10:31:31+00:00"


def test_to_contact_prefers_display_and_normalizes_empty_email():
    contact = RestNetboxClient._to_contact(_contact_record(display="Anna Schmidt", email=""))
    assert contact.name == "Anna Schmidt"
    assert contact.email is None

    contact = RestNetboxClient._to_contact(_contact_record(display=None, name="anna-schmidt"))
    assert contact.name == "anna-schmidt"


# --- reads -------------------------------------------------------------------


def test_get_contact_found_and_not_found():
    client = _client(contacts=FakeEndpoint(get_result=_contact_record()))
    contact = client.get_contact(1)
    assert contact is not None and contact.name == "Anna Schmidt"

    client = _client(contacts=FakeEndpoint(get_result=None))
    assert client.get_contact(999) is None


def test_get_contact_wraps_request_error():
    client = _client(contacts=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="Contact 1"):
        client.get_contact(1)


def test_search_contacts_passes_query_and_limit():
    endpoint = FakeEndpoint(filter_result=[_contact_record()])
    client = _client(contacts=endpoint)
    results = client.search_contacts("anna", limit=5)
    assert [c.name for c in results] == ["Anna Schmidt"]
    assert endpoint.calls == [("filter", (), {"q": "anna", "limit": 5})]


def test_search_contacts_wraps_request_error():
    client = _client(contacts=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="Contact-Suche"):
        client.search_contacts("anna", limit=5)


def test_list_vms_by_owner_filters_on_custom_field_and_rechecks_client_side():
    matching = FakeVmRecord(id=101, custom_fields={OWNER_FIELD: {"id": 3, "display": "T. Weber"}})
    # simulates NetBox's cf filter matching more loosely than plain equality
    stray = FakeVmRecord(id=102, custom_fields={OWNER_FIELD: {"id": 4, "display": "Someone Else"}})
    unowned = FakeVmRecord(id=103, custom_fields={})
    endpoint = FakeEndpoint(filter_result=[matching, stray, unowned])
    client = _client(vms=endpoint)

    vms = client.list_vms_by_owner(3)
    assert [vm.id for vm in vms] == [101]  # defensive re-check dropped the strays
    assert endpoint.calls == [("filter", (), {f"cf_{OWNER_FIELD}": 3})]


def test_list_vms_by_owner_wraps_request_error():
    client = _client(vms=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="VM-Liste"):
        client.list_vms_by_owner(3)


def test_get_vm_found_not_found_and_error():
    client = _client(vms=FakeEndpoint(get_result=FakeVmRecord(id=101)))
    assert client.get_vm(101).id == 101

    client = _client(vms=FakeEndpoint(get_result=None))
    assert client.get_vm(999) is None

    client = _client(vms=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="VM 101"):
        client.get_vm(101)


def test_list_vms_with_owner_drops_unowned_vms():
    owned = FakeVmRecord(id=101, custom_fields={OWNER_FIELD: {"id": 1, "display": "M. Brandt"}})
    unowned = FakeVmRecord(id=102, custom_fields={})
    client = _client(vms=FakeEndpoint(all_result=[owned, unowned]))
    assert [vm.id for vm in client.list_vms_with_owner()] == [101]


def test_list_vms_with_owner_wraps_request_error():
    client = _client(vms=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError):
        client.list_vms_with_owner()


# --- writes ------------------------------------------------------------------


def test_update_vm_owner_writes_custom_field_and_saves():
    record = FakeVmRecord(id=101, custom_fields={OWNER_FIELD: {"id": 1, "display": "M. Brandt"}})
    client = _client(vms=FakeEndpoint(get_result=record))
    client.update_vm_owner(101, 3)
    assert record.custom_fields[OWNER_FIELD] == 3  # written as plain id, not nested object
    assert record.saved


def test_update_vm_owner_raises_when_vm_missing():
    client = _client(vms=FakeEndpoint(get_result=None))
    with pytest.raises(NetboxError, match="nicht gefunden"):
        client.update_vm_owner(999, 3)


def test_update_vm_owner_raises_when_netbox_rejects_save():
    record = FakeVmRecord(id=101, save_ok=False)
    client = _client(vms=FakeEndpoint(get_result=record))
    with pytest.raises(NetboxError, match="abgelehnt"):
        client.update_vm_owner(101, 3)


def test_update_vm_owner_wraps_request_error():
    client = _client(vms=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="Owner-Änderung"):
        client.update_vm_owner(101, 3)


def test_create_journal_entry_targets_the_vm_object():
    endpoint = FakeEndpoint()
    client = _client(journal=endpoint)
    client.create_journal_entry(101, "Product Owner geändert ...")
    assert endpoint.calls == [
        (
            "create",
            (),
            {
                "assigned_object_type": "virtualization.virtualmachine",
                "assigned_object_id": 101,
                "kind": "info",
                "comments": "Product Owner geändert ...",
            },
        )
    ]


def test_create_journal_entry_wraps_request_error():
    client = _client(journal=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="Journal-Eintrag"):
        client.create_journal_entry(101, "x")


def test_update_vm_recertification_writes_all_three_fields_and_saves():
    record = FakeVmRecord(id=101)
    client = _client(vms=FakeEndpoint(get_result=record))
    client.update_vm_recertification(101, False, "kann weg", "2026-07-08T10:00:00+00:00")
    assert record.custom_fields[STILL_IN_USE_FIELD] is False
    assert record.custom_fields[COMMENT_FIELD] == "kann weg"
    assert record.custom_fields[REZERT_DATE_FIELD] == "2026-07-08T10:00:00+00:00"
    assert record.saved


def test_update_vm_recertification_raises_when_vm_missing():
    client = _client(vms=FakeEndpoint(get_result=None))
    with pytest.raises(NetboxError, match="nicht gefunden"):
        client.update_vm_recertification(999, True, "", "2026-07-08T10:00:00+00:00")


def test_update_vm_recertification_raises_when_netbox_rejects_save():
    record = FakeVmRecord(id=101, save_ok=False)
    client = _client(vms=FakeEndpoint(get_result=record))
    with pytest.raises(NetboxError, match="abgelehnt"):
        client.update_vm_recertification(101, True, "", "2026-07-08T10:00:00+00:00")


def test_update_vm_recertification_wraps_request_error():
    client = _client(vms=FakeEndpoint(raise_error=True))
    with pytest.raises(NetboxError, match="Rezertifizierung"):
        client.update_vm_recertification(101, True, "", "2026-07-08T10:00:00+00:00")
