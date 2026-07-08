import random

from app.netbox_real import OWNER_FIELD
from scripts.seed_netbox import build_contacts, build_vms, chunked, looks_unconfigured


def test_chunked_splits_into_expected_sizes():
    items = list(range(250))
    chunks = chunked(items, 100)
    assert [len(c) for c in chunks] == [100, 100, 50]
    assert sum(chunks, []) == items


def test_chunked_empty_input():
    assert chunked([], 100) == []


def test_build_contacts_generates_expected_count_and_shape():
    contacts = build_contacts(50, tag_id=7)
    assert len(contacts) == 50
    assert contacts[0]["name"] == "Testkontakt 01"
    assert contacts[-1]["name"] == "Testkontakt 50"
    assert all(c["tags"] == [7] for c in contacts)
    assert all("@" in c["email"] for c in contacts)


def test_build_vms_assigns_owner_from_given_contacts_only():
    contact_ids = [101, 102, 103]
    vms = build_vms(1000, cluster_id=5, contact_ids=contact_ids, tag_id=9, rng=random.Random(42))
    assert len(vms) == 1000
    assert all(vm["custom_fields"][OWNER_FIELD] in contact_ids for vm in vms)
    assert all(vm["cluster"] == 5 for vm in vms)
    assert all(vm["tags"] == [9] for vm in vms)
    # every contact should actually get used across 1000 VMs
    used_owners = {vm["custom_fields"][OWNER_FIELD] for vm in vms}
    assert used_owners == set(contact_ids)


def test_build_vms_rejects_empty_contact_list():
    import pytest

    with pytest.raises(ValueError):
        build_vms(10, cluster_id=1, contact_ids=[], tag_id=1, rng=random.Random(0))


def test_looks_unconfigured_detects_placeholder():
    assert looks_unconfigured("https://netbox.internal.example.com", "sometoken") is True
    assert looks_unconfigured("https://netbox.real.company.tld", "") is True
    assert looks_unconfigured("https://netbox.real.company.tld", "changeme") is True
    assert looks_unconfigured("https://netbox.real.company.tld", "realtoken123") is False
