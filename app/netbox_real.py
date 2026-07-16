"""Real NetBox backend, built on pynetbox.

Kept deliberately thin: all business logic lives in the routers, this module
only translates between pynetbox records and our Contact/Vm schemas and
converts failures into NetboxError so callers never fail silently.
"""

import pynetbox
from pynetbox.core.query import RequestError

from app.netbox_client import NetboxClient, NetboxError
from app.schemas import Contact, Vm

OWNER_FIELD = "cf_product_owner"
STILL_IN_USE_FIELD = "cf_still_in_use"
COMMENT_FIELD = "cf_vm_comment"
REZERT_DATE_FIELD = "cf_rezert_date"


class RestNetboxClient(NetboxClient):
    def __init__(self, url: str, token: str, ssl_verify: bool = True) -> None:
        self._api = pynetbox.api(url, token=token)
        if not ssl_verify:
            self._api.http_session.verify = False
        self._web_url = url.rstrip("/")

    def _vm_web_url(self, vm_id: int) -> str:
        return f"{self._web_url}/virtualization/virtual-machines/{vm_id}/"

    def _to_vm(self, record) -> Vm:
        owner_field = record.custom_fields.get(OWNER_FIELD)
        owner_id = owner_field.get("id") if owner_field else None
        owner_name = owner_field.get("display") if owner_field else None
        return Vm(
            id=record.id,
            name=record.name,
            owner_contact_id=owner_id,
            owner_contact_name=owner_name,
            vcpus=float(record.vcpus) if record.vcpus is not None else None,
            memory_gb=(record.memory / 1024) if record.memory is not None else None,
            disk_gb=float(record.disk) if record.disk is not None else None,
            netbox_url=self._vm_web_url(record.id),
            still_in_use=record.custom_fields.get(STILL_IN_USE_FIELD),
            comment=record.custom_fields.get(COMMENT_FIELD),
            rezert_date=record.custom_fields.get(REZERT_DATE_FIELD),
        )

    @staticmethod
    def _to_contact(record) -> Contact:
        email = getattr(record, "email", None) or None
        return Contact(id=record.id, name=record.display or record.name, email=email)

    def get_contact(self, contact_id: int) -> Contact | None:
        try:
            record = self._api.tenancy.contacts.get(contact_id)
        except RequestError as exc:
            raise NetboxError(f"Contact {contact_id} konnte nicht geladen werden: {exc}") from exc
        return self._to_contact(record) if record else None

    def search_contacts(self, query: str, limit: int) -> list[Contact]:
        try:
            records = self._api.tenancy.contacts.filter(q=query, limit=limit)
        except RequestError as exc:
            raise NetboxError(f"Contact-Suche fehlgeschlagen: {exc}") from exc
        return [self._to_contact(r) for r in records]

    def list_vms_by_owner(self, contact_id: int) -> list[Vm]:
        try:
            records = self._api.virtualization.virtual_machines.filter(
                **{f"cf_{OWNER_FIELD}": contact_id}
            )
        except RequestError as exc:
            raise NetboxError(f"VM-Liste konnte nicht geladen werden: {exc}") from exc
        # Defensive re-check in case the custom-field filter semantics differ
        # from a plain equality match on the NetBox instance in use.
        return [
            vm
            for vm in (self._to_vm(r) for r in records)
            if vm.owner_contact_id == contact_id
        ]

    def get_vm(self, vm_id: int) -> Vm | None:
        try:
            record = self._api.virtualization.virtual_machines.get(vm_id)
        except RequestError as exc:
            raise NetboxError(f"VM {vm_id} konnte nicht geladen werden: {exc}") from exc
        return self._to_vm(record) if record else None

    def list_vms_with_owner(self) -> list[Vm]:
        try:
            records = self._api.virtualization.virtual_machines.all()
        except RequestError as exc:
            raise NetboxError(f"VM-Liste konnte nicht geladen werden: {exc}") from exc
        vms = [self._to_vm(r) for r in records]
        return [vm for vm in vms if vm.owner_contact_id is not None]

    def update_vm_owner(self, vm_id: int, new_contact_id: int) -> None:
        try:
            record = self._api.virtualization.virtual_machines.get(vm_id)
            if record is None:
                raise NetboxError(f"VM {vm_id} nicht gefunden")
            record.custom_fields[OWNER_FIELD] = new_contact_id
            if not record.save():
                raise NetboxError(f"NetBox hat die Änderung an VM {vm_id} abgelehnt")
        except RequestError as exc:
            raise NetboxError(f"Owner-Änderung für VM {vm_id} fehlgeschlagen: {exc}") from exc

    def create_journal_entry(self, vm_id: int, comment: str) -> None:
        try:
            self._api.extras.journal_entries.create(
                assigned_object_type="virtualization.virtualmachine",
                assigned_object_id=vm_id,
                kind="info",
                comments=comment,
            )
        except RequestError as exc:
            raise NetboxError(f"Journal-Eintrag für VM {vm_id} fehlgeschlagen: {exc}") from exc

    def update_vm_recertification(
        self, vm_id: int, still_in_use: bool, comment: str, rezert_date: str
    ) -> None:
        try:
            record = self._api.virtualization.virtual_machines.get(vm_id)
            if record is None:
                raise NetboxError(f"VM {vm_id} nicht gefunden")
            record.custom_fields[STILL_IN_USE_FIELD] = still_in_use
            record.custom_fields[COMMENT_FIELD] = comment
            record.custom_fields[REZERT_DATE_FIELD] = rezert_date
            if not record.save():
                raise NetboxError(f"NetBox hat die Rezertifizierung von VM {vm_id} abgelehnt")
        except RequestError as exc:
            raise NetboxError(f"Rezertifizierung von VM {vm_id} fehlgeschlagen: {exc}") from exc
