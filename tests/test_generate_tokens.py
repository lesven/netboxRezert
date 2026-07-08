import csv

from app import db
from scripts.generate_tokens import generate_tokens


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
