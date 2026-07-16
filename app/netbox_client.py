from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import get_settings
from app.schemas import Contact, Vm


class NetboxError(Exception):
    """Raised whenever the NetBox API can't fulfil a request.

    Callers must surface this to the user (no silent data loss) rather than
    swallowing it.
    """


class NetboxClient(ABC):
    @abstractmethod
    def get_contact(self, contact_id: int) -> Contact | None: ...

    @abstractmethod
    def search_contacts(self, query: str, limit: int) -> list[Contact]: ...

    @abstractmethod
    def list_vms_by_owner(self, contact_id: int) -> list[Vm]: ...

    @abstractmethod
    def get_vm(self, vm_id: int) -> Vm | None: ...

    @abstractmethod
    def list_vms_with_owner(self) -> list[Vm]:
        """All VMs that currently have a vm_product_owner set.

        Used only by the token-generation batch script, not the web app.
        """

    @abstractmethod
    def update_vm_owner(self, vm_id: int, new_contact_id: int) -> None: ...

    @abstractmethod
    def create_journal_entry(self, vm_id: int, comment: str) -> None: ...

    @abstractmethod
    def update_vm_recertification(
        self, vm_id: int, still_in_use: bool, comment: str, rezert_date: str
    ) -> None:
        """Write vm_still_in_use/vm_comment/vm_rezert_date. No journal entry -
        this is a deliberately separate, unaudited write path (see CLAUDE.md).
        """


@lru_cache
def get_netbox_client() -> NetboxClient:
    settings = get_settings()
    if settings.netbox_mock:
        from app.netbox_mock import MockNetboxClient

        return MockNetboxClient()
    from app.netbox_real import RestNetboxClient

    return RestNetboxClient(url=settings.netbox_url, token=settings.netbox_token, ssl_verify=settings.netbox_ssl_verify)
