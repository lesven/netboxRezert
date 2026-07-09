"""End-to-end integration tests driving multiple endpoints in sequence
against the mock NetBox client, the way a real browser session would.
"""

from tests.conftest import issue_token


def test_full_owner_reassignment_lifecycle(client, netbox):
    old_owner_token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    new_owner_token = issue_token(3, "Tobias Weber")

    list_resp = client.get(f"/r/{old_owner_token}")
    assert "vm-erp-prod-01" in list_resp.text

    confirm_resp = client.post(f"/r/{old_owner_token}/confirm", data={"owner_101": "3"})
    assert confirm_resp.status_code == 200
    assert "vm-erp-prod-01" in confirm_resp.text
    assert "Tobias Weber" in confirm_resp.text

    save_resp = client.post(
        f"/r/{old_owner_token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt (Bereichsleiter IT)"],
            "new_contact_id": ["3"],
            "new_contact_name": ["Tobias Weber"],
        },
    )
    assert "✅" in save_resp.text

    old_owner_list = client.get(f"/r/{old_owner_token}")
    assert "vm-erp-prod-01" not in old_owner_list.text

    new_owner_list = client.get(f"/r/{new_owner_token}")
    assert "vm-erp-prod-01" in new_owner_list.text

    assert netbox._journal
    vm_id, comment = netbox._journal[-1]
    assert vm_id == 101
    assert "Michael Brandt" in comment
    assert "Tobias Weber" in comment


def test_bulk_reassignment_moves_every_selected_vm_and_leaves_rest_untouched(client, netbox):
    old_owner_token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    new_owner_token = issue_token(4, "Julia Krüger")

    save_resp = client.post(
        f"/r/{old_owner_token}/save",
        data={
            "vm_id": ["101", "102", "103"],
            "vm_name": ["vm-erp-prod-01", "vm-erp-prod-02", "vm-fileserver-03"],
            "old_contact_id": ["1", "1", "1"],
            "old_contact_name": ["Michael Brandt", "Michael Brandt", "Michael Brandt"],
            "new_contact_id": ["4", "4", "4"],
            "new_contact_name": ["Julia Krüger", "Julia Krüger", "Julia Krüger"],
        },
    )
    assert save_resp.text.count("✅") == 3

    old_owner_list = client.get(f"/r/{old_owner_token}").text
    assert "vm-erp-prod-01" not in old_owner_list
    assert "vm-erp-prod-02" not in old_owner_list
    assert "vm-fileserver-03" not in old_owner_list
    # not part of the bulk selection -> must still belong to the old owner
    assert "vm-webshop-frontend" in old_owner_list

    new_owner_list = client.get(f"/r/{new_owner_token}").text
    assert "vm-erp-prod-01" in new_owner_list
    assert "vm-erp-prod-02" in new_owner_list
    assert "vm-fileserver-03" in new_owner_list

    assert len(netbox._journal) == 3


def test_recertification_persists_across_requests_and_leaves_other_vms_alone(client, netbox):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")

    client.post(
        f"/r/{token}/recertify",
        data={"recert_101": "ja", "comment_101": "läuft weiter"},
    )

    list_resp = client.get(f"/r/{token}").text
    assert "läuft weiter" in list_resp

    vm_101 = netbox.get_vm(101)
    vm_102 = netbox.get_vm(102)
    assert vm_101.still_in_use is True
    assert vm_102.still_in_use is None  # untouched by the earlier request

    assert len(netbox._journal) == 1


def test_owner_reassignment_and_recertification_are_independent_journal_trails(client, netbox):
    old_owner_token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")
    new_owner_token = issue_token(3, "Tobias Weber")

    client.post(
        f"/r/{old_owner_token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt"],
            "new_contact_id": ["3"],
            "new_contact_name": ["Tobias Weber"],
        },
    )
    client.post(
        f"/r/{new_owner_token}/recertify",
        data={"recert_101": "ja", "comment_101": "nach Übernahme geprüft"},
    )

    vm = netbox.get_vm(101)
    assert vm.owner_contact_id == 3  # owner change stuck
    assert vm.still_in_use is True  # recert change stuck too, independently

    assert len(netbox._journal) == 2
    owner_comment = netbox._journal[0][1]
    recert_comment = netbox._journal[1][1]
    assert "Product Owner geändert" in owner_comment
    assert "Rezertifizierung durchgeführt" in recert_comment
    assert "Tobias Weber" in recert_comment  # triggered via the new owner's link


def test_search_then_reassign_using_returned_contact_id(client, netbox):
    token = issue_token(1, "Michael Brandt (Bereichsleiter IT)")

    search_resp = client.get(f"/r/{token}/contacts/search", params={"q": "sarah"})
    results = search_resp.json()["results"]
    assert len(results) == 1
    target_contact_id = results[0]["id"]

    save_resp = client.post(
        f"/r/{token}/save",
        data={
            "vm_id": ["101"],
            "vm_name": ["vm-erp-prod-01"],
            "old_contact_id": ["1"],
            "old_contact_name": ["Michael Brandt"],
            "new_contact_id": [str(target_contact_id)],
            "new_contact_name": [results[0]["name"]],
        },
    )
    assert "✅" in save_resp.text
    assert netbox.get_vm(101).owner_contact_id == target_contact_id
