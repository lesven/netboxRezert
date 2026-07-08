from pydantic import BaseModel


class Contact(BaseModel):
    id: int
    name: str
    email: str | None = None


class Vm(BaseModel):
    id: int
    name: str
    owner_contact_id: int | None
    owner_contact_name: str | None
    vcpus: float | None
    memory_gb: float | None
    disk_gb: float | None
    netbox_url: str | None = None
    still_in_use: bool | None = None
    comment: str | None = None
    rezert_date: str | None = None


class OwnerChange(BaseModel):
    vm_id: int
    vm_name: str
    old_contact_id: int | None
    old_contact_name: str | None
    new_contact_id: int
    new_contact_name: str


class SaveResult(BaseModel):
    change: OwnerChange
    success: bool
    error: str | None = None
    journal_error: str | None = None


class RecertChange(BaseModel):
    vm_id: int
    vm_name: str
    still_in_use: bool
    comment: str


class RecertSaveResult(BaseModel):
    change: RecertChange
    success: bool
    error: str | None = None
    journal_error: str | None = None
