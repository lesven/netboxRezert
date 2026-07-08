import re

from app.netbox_client import NetboxError
from app.routers.owner import _format_date_de
from tests.conftest import issue_token
from tests.test_confirm_and_save import _FailingClient


def test_list_page_shows_recert_controls(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}")
    assert resp.status_code == 200
    assert 'name="recert_101"' in resp.text
    assert 'name="comment_101"' in resp.text
    assert "recert-submit-btn" in resp.text


def test_format_date_de():
    assert _format_date_de("2026-07-08T10:31:31.769558+00:00") == "08.07.2026"
    assert _format_date_de("2026-01-05") == "05.01.2026"
    assert _format_date_de(None) == "–"
    assert _format_date_de("") == "–"
    assert _format_date_de("kaputt") == "kaputt"  # falls back to raw value, never crashes


def test_list_page_shows_rezert_date_as_dd_mm_yyyy(client):
    token = issue_token(1, "Michael Brandt")
    client.post(f"/r/{token}/recertify", data={"recert_101": "ja"})

    resp = client.get(f"/r/{token}")
    assert resp.status_code == 200
    row = re.search(r'<tr class="recert-row" data-vm-id="101"[^>]*>.*?</tr>', resp.text, re.S).group(0)
    cells = re.findall(r"<td>(.*?)</td>", row, re.S)
    # columns: name, vcpus, ram, disk, rezert_date, comment
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cells[4].strip())


def test_untouched_rows_are_left_alone(client, netbox):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/recertify",
        data={"recert_101": "ja", "comment_101": "läuft weiter"},
        # 102 deliberately omitted entirely, simulating an untouched row
    )
    assert resp.status_code == 200
    assert "✅" in resp.text

    vm_101 = netbox.get_vm(101)
    assert vm_101.still_in_use is True
    assert vm_101.comment == "läuft weiter"
    assert vm_101.rezert_date is not None

    vm_102 = netbox.get_vm(102)
    assert vm_102.still_in_use is None
    assert vm_102.rezert_date is None


def test_empty_string_value_is_not_touched(client, netbox):
    # tri-state default ("") must never be treated as an explicit "nein"
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={"recert_101": ""})
    assert resp.status_code == 200
    assert "Keine Rezertifizierung ausgewählt" in resp.text
    assert netbox.get_vm(101).still_in_use is None


def test_recertify_no_longer_needed(client, netbox):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/recertify",
        data={"recert_104": "nein", "comment_104": "kann abgeschaltet werden"},
    )
    assert resp.status_code == 200
    assert "nicht mehr benötigt" in resp.text
    vm = netbox.get_vm(104)
    assert vm.still_in_use is False
    assert vm.comment == "kann abgeschaltet werden"


def test_recertify_multiple_vms_independently(client, netbox):
    token = issue_token(1, "Michael Brandt")
    resp = client.post(
        f"/r/{token}/recertify",
        data={
            "recert_101": "ja",
            "recert_102": "nein",
            "recert_103": "",  # untouched despite being present with empty value
        },
    )
    assert resp.status_code == 200
    assert resp.text.count("✅") == 2
    assert netbox.get_vm(101).still_in_use is True
    assert netbox.get_vm(102).still_in_use is False
    assert netbox.get_vm(103).still_in_use is None


def test_recertification_writes_journal_entry_but_leaves_owner_untouched(client, netbox):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    resp = client.post(
        f"/r/{token}/recertify",
        data={"recert_101": "ja", "comment_101": "läuft weiter"},
    )
    assert resp.status_code == 200

    assert netbox.get_vm(101).owner_contact_id == 1  # owner untouched

    assert netbox._journal, "journal entry was not recorded"
    vm_id, journal_comment = netbox._journal[-1]
    assert vm_id == 101
    assert "Rezertifizierungstool" in journal_comment
    assert "Michael Brandt" in journal_comment  # who triggered it, via the link
    assert "Ja" in journal_comment
    assert "läuft weiter" in journal_comment


def test_recertify_surfaces_netbox_errors(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _FailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={"recert_101": "ja"})
    assert resp.status_code == 200
    assert "❌" in resp.text


class _RecertFailingClient(_FailingClient):
    def get_vm(self, vm_id):
        raise NetboxError("get_vm kaputt")


class _RecertJournalFailingClient(_FailingClient):
    def update_vm_recertification(self, vm_id, still_in_use, comment, rezert_date):
        return None

    def create_journal_entry(self, vm_id, comment):
        raise NetboxError("Journal-Endpoint down")


def test_recertify_warns_when_journal_entry_fails_but_data_was_saved(client, monkeypatch):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _RecertJournalFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={"recert_101": "ja"})
    assert resp.status_code == 200
    assert "✅" in resp.text  # the recertification itself succeeded
    assert "Audit-Journal-Eintrag konnte nicht geschrieben werden" in resp.text


def test_recertify_surfaces_get_vm_errors_without_losing_other_rows(client, monkeypatch, netbox):
    monkeypatch.setattr("app.routers.owner.get_netbox_client", lambda: _RecertFailingClient())
    token = issue_token(1, "Michael Brandt")
    resp = client.post(f"/r/{token}/recertify", data={"recert_101": "ja", "recert_102": "ja"})
    assert resp.status_code == 200
    assert resp.text.count("❌") == 2
