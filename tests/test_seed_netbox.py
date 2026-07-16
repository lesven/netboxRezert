import random
from types import SimpleNamespace

import pytest

from app.netbox_real import OWNER_FIELD
from scripts.seed_netbox import (
    SEED_TAG,
    build_contacts,
    build_vms,
    chunked,
    ensure_cluster,
    ensure_owner_custom_field,
    ensure_tag,
    looks_unconfigured,
    main,
    seed,
    wipe_previous_seed,
)


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


# --- pynetbox-level setup helpers, tested against an in-memory fake nb -------


class _FakeEndpoint:
    def __init__(self, existing=None, filter_items=(), create_raises=None):
        self._existing = existing
        self._filter_items = list(filter_items)
        self._create_raises = create_raises
        self.created: list = []
        self._next_id = 1000

    def get(self, *args, **kwargs):
        return self._existing

    def filter(self, *args, **kwargs):
        return iter(self._filter_items)

    def create(self, payload=None, **kwargs):
        if self._create_raises is not None:
            raise self._create_raises
        if isinstance(payload, list):  # bulk create (chunks)
            self.created.extend(payload)
            objs = []
            for _ in payload:
                self._next_id += 1
                objs.append(SimpleNamespace(id=self._next_id))
            return objs
        self.created.append(kwargs or payload)
        self._next_id += 1
        return SimpleNamespace(id=self._next_id)


class _Deletable:
    def __init__(self):
        self.deleted = False

    def delete(self):
        self.deleted = True


def _fake_nb(
    tags=None, custom_fields=None, cluster_types=None, clusters=None, vms=None, contacts=None
):
    return SimpleNamespace(
        extras=SimpleNamespace(
            tags=tags or _FakeEndpoint(),
            custom_fields=custom_fields or _FakeEndpoint(),
        ),
        virtualization=SimpleNamespace(
            cluster_types=cluster_types or _FakeEndpoint(),
            clusters=clusters or _FakeEndpoint(),
            virtual_machines=vms or _FakeEndpoint(),
        ),
        tenancy=SimpleNamespace(contacts=contacts or _FakeEndpoint()),
    )


def test_ensure_tag_reuses_existing_tag():
    existing = SimpleNamespace(id=7)
    endpoint = _FakeEndpoint(existing=existing)
    assert ensure_tag(_fake_nb(tags=endpoint)) is existing
    assert endpoint.created == []


def test_ensure_tag_creates_when_missing():
    endpoint = _FakeEndpoint(existing=None)
    tag = ensure_tag(_fake_nb(tags=endpoint))
    assert tag.id is not None
    assert endpoint.created[0]["slug"] == SEED_TAG


def test_ensure_cluster_creates_type_and_cluster_when_missing():
    cluster_types = _FakeEndpoint(existing=None)
    clusters = _FakeEndpoint(existing=None)
    tag = SimpleNamespace(id=7)
    cluster = ensure_cluster(_fake_nb(cluster_types=cluster_types, clusters=clusters), tag)
    assert cluster.id is not None
    assert len(cluster_types.created) == 1
    assert len(clusters.created) == 1
    # the created cluster must reference the freshly created type
    assert clusters.created[0]["type"] is not None


def test_ensure_cluster_reuses_existing_objects():
    existing = SimpleNamespace(id=42)
    clusters = _FakeEndpoint(existing=existing)
    nb = _fake_nb(cluster_types=_FakeEndpoint(existing=SimpleNamespace(id=5)), clusters=clusters)
    assert ensure_cluster(nb, SimpleNamespace(id=7)) is existing
    assert clusters.created == []


def test_ensure_owner_custom_field_is_noop_when_field_exists():
    endpoint = _FakeEndpoint(existing=SimpleNamespace(id=1))
    ensure_owner_custom_field(_fake_nb(custom_fields=endpoint))
    assert endpoint.created == []


def test_ensure_owner_custom_field_creates_object_type_field():
    endpoint = _FakeEndpoint(existing=None)
    ensure_owner_custom_field(_fake_nb(custom_fields=endpoint))
    payload = endpoint.created[0]
    assert payload["name"] == OWNER_FIELD
    assert payload["type"] == "object"
    assert payload["object_type"] == "tenancy.contact"
    assert payload["object_types"] == ["virtualization.virtualmachine"]


def test_ensure_owner_custom_field_gives_manual_instructions_on_api_rejection():
    from tests.test_netbox_real import _request_error

    endpoint = _FakeEndpoint(existing=None, create_raises=_request_error())
    with pytest.raises(RuntimeError, match="manuell anlegen"):
        ensure_owner_custom_field(_fake_nb(custom_fields=endpoint))


def test_wipe_previous_seed_deletes_tagged_objects_and_reports_counts():
    seed_vms = [_Deletable(), _Deletable(), _Deletable()]
    seed_contacts = [_Deletable()]
    nb = _fake_nb(
        vms=_FakeEndpoint(filter_items=seed_vms),
        contacts=_FakeEndpoint(filter_items=seed_contacts),
    )
    assert wipe_previous_seed(nb) == (3, 1)
    assert all(vm.deleted for vm in seed_vms)
    assert all(c.deleted for c in seed_contacts)


def test_seed_refuses_placeholder_settings(settings, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("NETBOX_URL", "https://demo.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "changeme")
    get_settings.cache_clear()
    try:
        assert seed(vm_count=10, contact_count=2) == 1
    finally:
        get_settings.cache_clear()


def test_seed_full_run_against_fake_netbox(settings, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("NETBOX_URL", "http://netbox.test")
    monkeypatch.setenv("NETBOX_TOKEN", "realtoken123")
    get_settings.cache_clear()

    vms = _FakeEndpoint(filter_items=[_Deletable()])  # one leftover VM from a previous run
    contacts = _FakeEndpoint()
    nb = _fake_nb(
        tags=_FakeEndpoint(existing=SimpleNamespace(id=7)),
        custom_fields=_FakeEndpoint(existing=SimpleNamespace(id=1)),
        cluster_types=_FakeEndpoint(existing=SimpleNamespace(id=5)),
        clusters=_FakeEndpoint(existing=SimpleNamespace(id=42)),
        vms=vms,
        contacts=contacts,
    )
    monkeypatch.setattr("scripts.seed_netbox.pynetbox.api", lambda url, token: nb)

    try:
        # 450 VMs -> exercises the 200er chunking (3 chunks) as well
        assert seed(vm_count=450, contact_count=10, seed_value=42) == 0
    finally:
        get_settings.cache_clear()

    assert len(contacts.created) == 10
    assert len(vms.created) == 450
    created_owner_ids = {vm["custom_fields"][OWNER_FIELD] for vm in vms.created}
    contact_ids = set(range(1001, 1011))  # ids minted by the fake contact endpoint
    assert created_owner_ids <= contact_ids


def test_main_aborts_without_explicit_ja(settings, monkeypatch):
    # the interactive safety gate before wiping/creating data in a real
    # instance: anything but ja/yes/y/j must abort with exit code 1
    monkeypatch.setattr("sys.argv", ["seed_netbox", "--vm-count", "5", "--contact-count", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: "nein")
    seed_called = False

    def _no_seed(*args, **kwargs):
        nonlocal seed_called
        seed_called = True
        return 0

    monkeypatch.setattr("scripts.seed_netbox.seed", _no_seed)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    assert not seed_called


def test_main_with_yes_flag_skips_prompt_and_runs_seed(settings, monkeypatch):
    monkeypatch.setattr("sys.argv", ["seed_netbox", "-y", "--vm-count", "5", "--contact-count", "2"])
    monkeypatch.setattr(
        "builtins.input", lambda prompt: pytest.fail("darf mit -y nie nach Bestätigung fragen")
    )
    captured = {}

    def _fake_seed(vm_count, contact_count, seed_value):
        captured.update(vm_count=vm_count, contact_count=contact_count, seed_value=seed_value)
        return 0

    monkeypatch.setattr("scripts.seed_netbox.seed", _fake_seed)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    assert captured == {"vm_count": 5, "contact_count": 2, "seed_value": None}
