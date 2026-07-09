import pytest
from pydantic import ValidationError

from app.schemas import Contact, OwnerChange, RecertChange, RecertSaveResult, SaveResult, Vm


def test_contact_email_defaults_to_none():
    contact = Contact(id=1, name="Anna Schmidt")
    assert contact.email is None


def test_contact_requires_id_and_name():
    with pytest.raises(ValidationError):
        Contact(name="Anna Schmidt")


def test_vm_allows_unowned_and_missing_metrics():
    vm = Vm(
        id=1,
        name="vm-x",
        owner_contact_id=None,
        owner_contact_name=None,
        vcpus=None,
        memory_gb=None,
        disk_gb=None,
    )
    assert vm.owner_contact_id is None
    assert vm.netbox_url is None
    assert vm.still_in_use is None


def test_save_result_defaults_have_no_errors():
    change = OwnerChange(
        vm_id=1, vm_name="vm-x", old_contact_id=1, old_contact_name="A",
        new_contact_id=2, new_contact_name="B",
    )
    result = SaveResult(change=change, success=True)
    assert result.error is None
    assert result.journal_error is None


def test_recert_save_result_defaults_have_no_errors():
    change = RecertChange(vm_id=1, vm_name="vm-x", still_in_use=True, comment="")
    result = RecertSaveResult(change=change, success=True)
    assert result.error is None
    assert result.journal_error is None
