"""In-memory NetBox stand-in for local development and tests.

Mirrors the bulk-assignment situation described in the requirements doc:
most VMs sit under one department head (Bereichsleiter), and reassignment
should spread them across the actual technical owners.
"""

from app.netbox_client import NetboxClient
from app.schemas import Contact, Vm

_CONTACTS: dict[int, Contact] = {
    1: Contact(id=1, name="Michael Brandt (Bereichsleiter IT)", email="m.brandt@example.com"),
    2: Contact(id=2, name="Anna Schmidt", email="a.schmidt@example.com"),
    3: Contact(id=3, name="Tobias Weber", email="t.weber@example.com"),
    4: Contact(id=4, name="Julia Krüger", email="j.krueger@example.com"),
    5: Contact(id=5, name="Peter Hoffmann", email="p.hoffmann@example.com"),
    6: Contact(id=6, name="Sarah Nguyen", email="s.nguyen@example.com"),
    7: Contact(id=7, name="David Fischer", email="d.fischer@example.com"),
}

_VMS: dict[int, dict] = {
    101: {"name": "vm-erp-prod-01", "owner": 1, "vcpus": 8, "memory_gb": 32, "disk_gb": 500},
    102: {"name": "vm-erp-prod-02", "owner": 1, "vcpus": 8, "memory_gb": 32, "disk_gb": 500},
    103: {"name": "vm-fileserver-03", "owner": 1, "vcpus": 4, "memory_gb": 16, "disk_gb": 2000},
    104: {"name": "vm-webshop-frontend", "owner": 1, "vcpus": 2, "memory_gb": 8, "disk_gb": 80},
    105: {"name": "vm-webshop-backend", "owner": 1, "vcpus": 4, "memory_gb": 16, "disk_gb": 160},
    106: {"name": "vm-reporting-01", "owner": 2, "vcpus": 4, "memory_gb": 16, "disk_gb": 250},
}


class MockNetboxClient(NetboxClient):
    def __init__(self) -> None:
        self._contacts = dict(_CONTACTS)
        self._vms = {vid: dict(v) for vid, v in _VMS.items()}
        self._journal: list[tuple[int, str]] = []

    def get_contact(self, contact_id: int) -> Contact | None:
        return self._contacts.get(contact_id)

    def search_contacts(self, query: str, limit: int) -> list[Contact]:
        q = query.strip().lower()
        matches = [c for c in self._contacts.values() if q in c.name.lower()]
        return matches[:limit]

    def _to_vm(self, vm_id: int, data: dict) -> Vm:
        owner_id = data["owner"]
        owner = self._contacts.get(owner_id) if owner_id else None
        return Vm(
            id=vm_id,
            name=data["name"],
            owner_contact_id=owner_id,
            owner_contact_name=owner.name if owner else None,
            vcpus=data["vcpus"],
            memory_gb=data["memory_gb"],
            disk_gb=data["disk_gb"],
            netbox_url=f"http://mock-netbox.local/virtualization/virtual-machines/{vm_id}/",
            still_in_use=data.get("still_in_use"),
            comment=data.get("comment"),
            rezert_date=data.get("rezert_date"),
        )

    def list_vms_by_owner(self, contact_id: int) -> list[Vm]:
        return [
            self._to_vm(vid, data)
            for vid, data in self._vms.items()
            if data["owner"] == contact_id
        ]

    def get_vm(self, vm_id: int) -> Vm | None:
        data = self._vms.get(vm_id)
        return self._to_vm(vm_id, data) if data else None

    def list_vms_with_owner(self) -> list[Vm]:
        return [self._to_vm(vid, data) for vid, data in self._vms.items() if data["owner"]]

    def update_vm_owner(self, vm_id: int, new_contact_id: int) -> None:
        if vm_id not in self._vms:
            from app.netbox_client import NetboxError

            raise NetboxError(f"VM {vm_id} nicht gefunden")
        if new_contact_id not in self._contacts:
            from app.netbox_client import NetboxError

            raise NetboxError(f"Contact {new_contact_id} nicht gefunden")
        self._vms[vm_id]["owner"] = new_contact_id

    def create_journal_entry(self, vm_id: int, comment: str) -> None:
        self._journal.append((vm_id, comment))

    def update_vm_recertification(
        self, vm_id: int, still_in_use: bool, comment: str, rezert_date: str
    ) -> None:
        if vm_id not in self._vms:
            from app.netbox_client import NetboxError

            raise NetboxError(f"VM {vm_id} nicht gefunden")
        self._vms[vm_id]["still_in_use"] = still_in_use
        self._vms[vm_id]["comment"] = comment
        self._vms[vm_id]["rezert_date"] = rezert_date
