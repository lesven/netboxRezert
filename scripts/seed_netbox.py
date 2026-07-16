"""Idempotent test-data seeder for a real NetBox test instance.

Creates N synthetic contacts and M synthetic VMs (default 50 / 1000) with a
random vm_product_owner assignment, so the recertification tool has
something realistic to reassign. Everything this script creates is tagged
`recert-seed-data`; every run first deletes anything carrying that tag and
then recreates it, so re-running is safe and never accumulates cruft or
touches unrelated data in the target instance.

Talks to pynetbox directly rather than through app.netbox_client, because it
needs admin-level setup (custom field, cluster, tags) the running app never
performs itself.

Usage:
    python -m scripts.seed_netbox --vm-count 1000 --contact-count 50
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pynetbox  # noqa: E402
from pynetbox.core.query import RequestError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.netbox_real import OWNER_FIELD  # noqa: E402

SEED_TAG = "recert-seed-data"
CLUSTER_TYPE_NAME = "Rezertifizierung-Test"
CLUSTER_TYPE_SLUG = "rezert-test"
CLUSTER_NAME = "Rezertifizierung-Test-Cluster"

VCPU_CHOICES = [1, 2, 4, 8, 16]
MEMORY_GB_CHOICES = [2, 4, 8, 16, 32, 64]
DISK_GB_CHOICES = [50, 100, 250, 500, 1000, 2000]

CHUNK_SIZE = 200


def chunked(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_contacts(count: int, tag_id: int) -> list[dict]:
    return [
        {
            "name": f"Testkontakt {i:02d}",
            "email": f"testkontakt{i:02d}@example.test",
            "tags": [tag_id],
        }
        for i in range(1, count + 1)
    ]


def build_vms(
    count: int, cluster_id: int, contact_ids: list[int], tag_id: int, rng: random.Random
) -> list[dict]:
    if not contact_ids:
        raise ValueError("contact_ids darf nicht leer sein")
    return [
        {
            "name": f"recert-test-vm-{i:04d}",
            "status": "active",
            "cluster": cluster_id,
            "vcpus": rng.choice(VCPU_CHOICES),
            "memory": rng.choice(MEMORY_GB_CHOICES) * 1024,  # NetBox stores memory in MB
            "disk": rng.choice(DISK_GB_CHOICES) * 1024,  # NetBox stores disk in MB
            "tags": [tag_id],
            "custom_fields": {OWNER_FIELD: rng.choice(contact_ids)},
        }
        for i in range(1, count + 1)
    ]


def ensure_tag(nb):
    tag = nb.extras.tags.get(slug=SEED_TAG)
    if tag is None:
        tag = nb.extras.tags.create(
            name=SEED_TAG,
            slug=SEED_TAG,
            color="9e9e9e",
            description="Von scripts/seed_netbox.py erzeugte Testdaten - sicher loeschbar",
        )
    return tag


def ensure_cluster(nb, tag):
    cluster_type = nb.virtualization.cluster_types.get(name=CLUSTER_TYPE_NAME)
    if cluster_type is None:
        cluster_type = nb.virtualization.cluster_types.create(
            name=CLUSTER_TYPE_NAME, slug=CLUSTER_TYPE_SLUG, tags=[tag.id]
        )
    cluster = nb.virtualization.clusters.get(name=CLUSTER_NAME)
    if cluster is None:
        cluster = nb.virtualization.clusters.create(name=CLUSTER_NAME, type=cluster_type.id, tags=[tag.id])
    return cluster


def ensure_owner_custom_field(nb) -> None:
    if nb.extras.custom_fields.get(name=OWNER_FIELD) is not None:
        return
    try:
        nb.extras.custom_fields.create(
            object_types=["virtualization.virtualmachine"],
            type="object",
            object_type="tenancy.contact",
            name=OWNER_FIELD,
            label="Product Owner",
            required=False,
        )
    except RequestError as exc:
        raise RuntimeError(
            f"Custom Field '{OWNER_FIELD}' existiert nicht und konnte nicht automatisch angelegt werden "
            f"({exc}). Bitte manuell anlegen: Extras > Custom Fields > Add - "
            f"Name: {OWNER_FIELD}, Type: Object, Related object type: Tenancy > Contact, "
            f"anwendbar auf: Virtualization > Virtual Machine."
        ) from exc


def wipe_previous_seed(nb) -> tuple[int, int]:
    vms = list(nb.virtualization.virtual_machines.filter(tag=SEED_TAG))
    for vm in vms:
        vm.delete()
    contacts = list(nb.tenancy.contacts.filter(tag=SEED_TAG))
    for contact in contacts:
        contact.delete()
    return len(vms), len(contacts)


def looks_unconfigured(netbox_url: str, netbox_token: str) -> bool:
    return "example.com" in netbox_url or not netbox_token or netbox_token == "changeme"


def seed(vm_count: int, contact_count: int, seed_value: int | None = None) -> int:
    settings = get_settings()
    if looks_unconfigured(settings.netbox_url, settings.netbox_token):
        print(
            "NETBOX_URL/NETBOX_TOKEN sehen nach Platzhalter-Werten aus - bitte .env prüfen.",
            file=sys.stderr,
        )
        return 1

    nb = pynetbox.api(settings.netbox_url, token=settings.netbox_token)
    rng = random.Random(seed_value)

    tag = ensure_tag(nb)
    ensure_owner_custom_field(nb)
    cluster = ensure_cluster(nb, tag)

    print(f"Entferne vorherige Seed-Daten (Tag '{SEED_TAG}')...")
    removed_vms, removed_contacts = wipe_previous_seed(nb)
    print(f"  {removed_vms} VM(s), {removed_contacts} Contact(s) entfernt.")

    print(f"Erzeuge {contact_count} Contacts...")
    created_contacts = []
    for chunk in chunked(build_contacts(contact_count, tag.id), CHUNK_SIZE):
        created_contacts.extend(nb.tenancy.contacts.create(chunk))
    contact_ids = [c.id for c in created_contacts]

    print(f"Erzeuge {vm_count} VMs...")
    vm_payloads = build_vms(vm_count, cluster.id, contact_ids, tag.id, rng)
    created = 0
    for chunk in chunked(vm_payloads, CHUNK_SIZE):
        nb.virtualization.virtual_machines.create(chunk)
        created += len(chunk)
        print(f"  {created}/{vm_count}")

    print("Fertig.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--vm-count", type=int, default=1000)
    parser.add_argument("--contact-count", type=int, default=50)
    parser.add_argument(
        "--seed", type=int, default=None, help="Zufalls-Seed für reproduzierbare Owner-Zuordnung"
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Sicherheitsabfrage überspringen")
    args = parser.parse_args()

    settings = get_settings()
    if not args.yes:
        print(f"Ziel: {settings.netbox_url}")
        print(f"Dies löscht vorhandene Seed-Testdaten (Tag '{SEED_TAG}') dort")
        print(f"und erzeugt {args.contact_count} Contacts + {args.vm_count} VMs neu.")
        confirm = input("Fortfahren? [ja/NEIN] ").strip().lower()
        if confirm not in ("ja", "yes", "y", "j"):
            print("Abgebrochen.")
            raise SystemExit(1)

    raise SystemExit(seed(args.vm_count, args.contact_count, args.seed))


if __name__ == "__main__":
    main()
