"""Batch-generate personalized recertification links.

Finds every contact that currently owns at least one VM (vm_product_owner
set) and ensures each has a token, reusing an existing one if already
present so re-running this script is idempotent and doesn't invalidate
links already sent out. Writes a CSV with one row per contact so the
results can be pasted into individual emails.

Usage:
    python -m scripts.generate_tokens [--output tokens.csv]
"""

import argparse
import csv
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import find_token_for_contact, init_db, store_token  # noqa: E402
from app.netbox_client import NetboxError, get_netbox_client  # noqa: E402


def generate_tokens(output_path: str) -> int:
    init_db()
    settings = get_settings()
    client = get_netbox_client()

    try:
        vms = client.list_vms_with_owner()
    except NetboxError as exc:
        print(f"Fehler beim Laden der VM-Liste aus NetBox: {exc}", file=sys.stderr)
        return 1

    contacts = {}
    for vm in vms:
        if vm.owner_contact_id is not None:
            contacts[vm.owner_contact_id] = vm.owner_contact_name or f"Contact #{vm.owner_contact_id}"

    if not contacts:
        print("Keine Contacts mit zugeordneten VMs gefunden.")
        return 0

    rows = []
    for contact_id, contact_name in sorted(contacts.items(), key=lambda kv: kv[1]):
        token = find_token_for_contact(contact_id)
        is_new = token is None
        if token is None:
            token = uuid.uuid4().hex
            store_token(token, contact_id, contact_name)
        rows.append(
            {
                "contact_id": contact_id,
                "contact_name": contact_name,
                "token": token,
                "url": f"{settings.base_url.rstrip('/')}/r/{token}",
                "neu_erzeugt": "ja" if is_new else "nein",
            }
        )

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["contact_id", "contact_name", "token", "url", "neu_erzeugt"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Link(s) geschrieben nach {output_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tokens.csv", help="Pfad der CSV-Ausgabedatei")
    args = parser.parse_args()
    raise SystemExit(generate_tokens(args.output))


if __name__ == "__main__":
    main()
