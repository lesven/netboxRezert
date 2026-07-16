import csv

import pytest

from app import db
from app.netbox_client import NetboxError
from app.schemas import Vm
from scripts.generate_tokens import generate_tokens, main
from tests.test_confirm_and_save import _FailingClient


def test_generate_tokens_creates_csv_for_owning_contacts(settings, tmp_path):
    output = tmp_path / "tokens.csv"
    exit_code = generate_tokens(str(output))
    assert exit_code == 0

    with open(output, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    contact_ids = {int(r["contact_id"]) for r in rows}
    # contacts 1 and 2 own VMs in the mock fixture; 7 (David Fischer) owns none
    assert contact_ids == {1, 2}
    for row in rows:
        assert row["url"].startswith("http://tool.internal/r/")
        assert row["neu_erzeugt"] == "ja"


def test_generate_tokens_is_idempotent(settings, tmp_path):
    output = tmp_path / "tokens.csv"
    generate_tokens(str(output))
    with open(output, newline="", encoding="utf-8") as f:
        first_run = {r["contact_id"]: r["token"] for r in csv.DictReader(f)}

    generate_tokens(str(output))
    with open(output, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        assert row["token"] == first_run[row["contact_id"]]
        assert row["neu_erzeugt"] == "nein"

    # and the DB itself only ever holds one token per contact
    assert len({r["contact_id"] for r in rows}) == len(db.list_tokens())


class _VmListFailingClient(_FailingClient):
    def list_vms_with_owner(self):
        raise NetboxError("NetBox antwortet nicht")


def test_generate_tokens_fails_cleanly_when_netbox_down(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.generate_tokens.get_netbox_client", lambda: _VmListFailingClient()
    )
    output = tmp_path / "tokens.csv"
    assert generate_tokens(str(output)) == 1
    assert not output.exists()  # no half-written CSV
    assert db.list_tokens() == []  # and no tokens minted


class _NoOwnedVmsClient(_FailingClient):
    def list_vms_with_owner(self):
        return []


def test_generate_tokens_with_no_owning_contacts_succeeds_without_csv(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setattr("scripts.generate_tokens.get_netbox_client", lambda: _NoOwnedVmsClient())
    output = tmp_path / "tokens.csv"
    assert generate_tokens(str(output)) == 0
    assert not output.exists()


class _NamelessOwnerClient(_FailingClient):
    def list_vms_with_owner(self):
        return [
            Vm(
                id=1, name="vm-x", owner_contact_id=9, owner_contact_name=None,
                vcpus=1, memory_gb=1, disk_gb=1,
            )
        ]


def test_generate_tokens_falls_back_to_contact_id_when_name_missing(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setattr("scripts.generate_tokens.get_netbox_client", lambda: _NamelessOwnerClient())
    output = tmp_path / "tokens.csv"
    assert generate_tokens(str(output)) == 0

    with open(output, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["contact_name"] == "Contact #9"


def test_main_parses_output_argument_and_exits_zero(settings, tmp_path, monkeypatch):
    output = tmp_path / "tokens.csv"
    monkeypatch.setattr("sys.argv", ["generate_tokens", "--output", str(output)])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    assert output.exists()
