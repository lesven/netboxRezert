from app import db


def test_store_token_roundtrips_via_resolve(settings):
    db.store_token("tok-1", 1, "Michael Brandt")
    assert db.resolve_token("tok-1") == 1


def test_resolve_unknown_token_is_none(settings):
    assert db.resolve_token("nope") is None


def test_find_token_for_contact_returns_none_when_absent(settings):
    assert db.find_token_for_contact(999) is None


def test_find_token_for_contact_returns_stored_token(settings):
    db.store_token("tok-1", 1, "Michael Brandt")
    assert db.find_token_for_contact(1) == "tok-1"


def test_store_token_upsert_keeps_original_token_but_updates_name(settings):
    # generate_tokens.py relies on this: re-running must never mint a second
    # token for a contact who already has one, even if their name changed.
    db.store_token("tok-1", 1, "Michael Brandt")
    db.store_token("tok-2", 1, "Michael B. Brandt")

    assert db.find_token_for_contact(1) == "tok-1"
    assert db.resolve_token("tok-2") is None
    rows = db.list_tokens()
    assert len(rows) == 1
    assert rows[0]["contact_name"] == "Michael B. Brandt"


def test_list_tokens_orders_by_contact_name(settings):
    db.store_token("tok-b", 2, "Bertha")
    db.store_token("tok-a", 1, "Anna")
    names = [row["contact_name"] for row in db.list_tokens()]
    assert names == ["Anna", "Bertha"]


def test_list_tokens_empty_when_no_tokens_issued(settings):
    assert db.list_tokens() == []


def test_init_db_is_idempotent(settings):
    db.init_db()
    db.init_db()  # must not raise on an already-existing table
    assert db.list_tokens() == []
