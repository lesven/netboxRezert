# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

Implemented v1, built against the requirements in `Anforderungsdokument_Netbox-Rezertifizierungstool.md` (still the source of truth for scope). No `git` repo has been initialized yet. Runs fully against an in-memory mock NetBox by default (`NETBOX_MOCK=true`), so it can be developed and tested without a real NetBox instance; a real instance has not yet been wired up/verified end-to-end.

> This project is **not** part of the PHP/Symfony workspace described in the parent `../../CLAUDE.md`. It is a standalone Python tool.

## What This Tool Is

A lightweight internal web tool for **reassigning the Product Owner of NetBox VMs** — nothing more. Many VMs are currently assigned in bulk to a department head instead of the actual technical owner. A Product Owner opens a personalized link, sees the VMs currently assigned to them, and picks a more precise owner per VM from the existing NetBox contacts.

It is a **reassignment tool, not a general CMDB frontend.** It only ever changes the `vm_product_owner` custom field on VM objects (plus writes a journal entry). Do not add editing of other fields or object types (physical devices, clusters, etc.) — those are explicitly out of scope for v1.

## Commands

```bash
make install         # create .venv, install requirements-dev.txt
make test             # pytest (runs entirely against the mock NetBox client)
make lint             # ruff check
make lint-fix         # ruff check --fix + ruff format
make typecheck        # mypy app

make up               # docker compose up -d --build (real NetBox, needs .env)
make down
make fresh            # down -v && up --build
make generate-tokens  # batch-create/reuse links, writes ./tokens.csv

# single test / filter
.venv/bin/pytest tests/test_confirm_and_save.py
.venv/bin/pytest -k test_save_updates_owner_and_writes_journal

# run dev server directly against the mock client
source .venv/bin/activate && uvicorn app.main:app --reload --port 8080
```

## Architecture

Stateless FastAPI app — no sessions, no cookies. Every request re-derives identity from the token in the URL path (`/r/{token}`), same "evidence lives in the request, not in server state" philosophy the workspace already uses for `c5Lifecycle`.

- **`app/db.py`** — the *only* first-party persistence: a single SQLite table mapping opaque `token → contact_id`. Everything else (VMs, contacts, ownership) is read fresh from NetBox on every request; nothing about VMs/contacts is cached or duplicated locally.
- **`app/netbox_client.py`** — abstract `NetboxClient` interface (`get_contact`, `search_contacts`, `list_vms_by_owner`, `get_vm`, `list_vms_with_owner`, `update_vm_owner`, `create_journal_entry`, `update_vm_recertification`) plus `NetboxError`. `get_netbox_client()` picks an implementation based on `settings.netbox_mock`:
  - **`app/netbox_mock.py`** — in-memory fixture (a handful of contacts/VMs mirroring the bulk-assignment scenario from the spec). Used for dev and the entire test suite.
  - **`app/netbox_real.py`** — real backend via `pynetbox`. Reads the owner custom field's nested object (`custom_fields["vm_product_owner"]`) directly off VM records rather than doing a second lookup per VM. Filters VMs server-side via `cf_vm_product_owner=<id>`, then re-checks the result client-side as a defensive belt-and-braces measure since NetBox's filtering semantics for object-type custom fields aren't something this codebase has verified against a real instance yet. The recertification fields (`vm_still_in_use`/`vm_comment`/`vm_rezert_date`) are plain scalar custom fields, read straight off `custom_fields` with no nested-object unwrapping needed.
- **`app/routers/owner.py`** — the whole request flow:
  1. `GET /r/{token}` — resolve token, list VMs owned by the resolved contact.
  2. `GET /r/{token}/contacts/search?q=` — JSON contact search (used by vanilla-JS autocomplete in `app/static/app.js`; deliberately not HTMX/CDN-based so the page has zero external dependencies, matching the no-internet-exposure requirement).
  3. `POST /r/{token}/confirm` — takes the submitted `owner_<vm_id>` fields, **re-fetches each VM fresh from NetBox** and diffs against the submission (never trusts client-submitted "old owner"), silently drops no-op rows, and renders the confirmation summary.
  4. `POST /r/{token}/save` — writes each change (`update_vm_owner` then `create_journal_entry`) and reports per-row success/failure. A failed journal write after a successful owner write is surfaced as a distinct warning, not silently dropped — the audit trail is a hard requirement, so a partial success must be visible.
  5. `POST /r/{token}/recertify` — **independent of the owner flow above**, per `Anforderungsdokument_rezert.md`. Writes `vm_still_in_use`/`vm_comment`/`vm_rezert_date` (the last is server-generated `datetime.now(UTC)`, never user input) directly in one step, with **no confirmation interstitial** (a deliberate scope decision — see Security Posture below) but **does write a journal entry** per VM (added after the fact, on request — journal parity with the owner flow, no confirm-dialog parity). Only rows where the tri-state `recert_<vm_id>` field is explicitly `"ja"`/`"nein"` are touched; the default `""` means "not reviewed this round" and must never be written as a value. A failed journal write after a successful data write surfaces as a distinct warning, same pattern as `/save`. NetBox errors are still caught and reported per VM (no silent data loss survives even without the confirm step).
- **`scripts/generate_tokens.py`** — finds every contact currently owning ≥1 VM, reuses an existing token if one exists (idempotent — safe to re-run without invalidating links already emailed out), writes a CSV of contact/token/URL.
- **`scripts/seed_netbox.py`** — admin-only test-data seeder, talks to `pynetbox` directly (not through `app/netbox_client.py`) since it needs setup the running app never does: creating the `vm_product_owner` custom field, a throwaway Cluster/ClusterType, N contacts and M VMs with random ownership. Everything it creates is tagged `recert-seed-data`; every run wipes anything with that tag first, so re-running is safe and never accumulates cruft. Always targets `NETBOX_URL`/`NETBOX_TOKEN` directly regardless of `NETBOX_MOCK` (seeding a mock makes no sense) and refuses to run against placeholder-looking settings. Run via `make seed-netbox` (needs the image rebuilt after this file was added — `make up` first).

Journal entry text follows the template from FA-5 in the spec verbatim (`"Product Owner geändert von {alt} zu {neu} durch Rezertifizierungstool (ausgelöst über Link von {Token-Contact})"`).

## Resolved Decisions (were open questions in the spec)

- **Token lifetime: permanent**, no expiry. There is deliberately no revoke/expiry column in the `tokens` table.
- **Save granularity: bulk.** Users can change any number of rows before a single confirm+save round-trip; there is no per-row save action.
- **Token generation/distribution:** not covered by the original spec at all — `scripts/generate_tokens.py` batch-generates for every contact that currently owns a VM, rather than an on-demand admin UI or per-contact CLI invocation. Re-running it is safe (existing tokens are reused).
- **Persistence:** SQLite (`DATABASE_PATH`, defaults to a file under `data/`) rather than Postgres — the only first-party state is a single token-mapping table, so a dedicated DB container was judged unnecessary.
- **`vm_still_in_use` UI is a tri-state select, not a checkbox.** A binary checkbox can't distinguish "explicitly marked not needed" from "never reviewed this round" (both render as unchecked), which would risk silently writing `false` for VMs nobody actually looked at. The select defaults to an empty value that means "leave untouched" and is excluded from the save entirely.
- **Recertification and owner reassignment are two separate tables/forms/buttons on the same page**, not merged into one shared table — asked and confirmed explicitly, not merged in for simplicity's sake. They now both write a journal entry; they still differ on the confirmation dialog (see Security Posture).

## Known Gaps / Not Yet Verified

- Never tested against a real NetBox instance — development so far is entirely against `netbox_mock.py`. Before going live, confirm: the `cf_vm_product_owner=<id>` filter syntax actually works on NetBox v4.2.9 for an object-type custom field; the nested custom-field object shape returned by the API (`id`/`display`) matches what `_to_vm` in `app/netbox_real.py` assumes; and that the contacts endpoint lives under `tenancy.contacts` (not e.g. a separate contacts plugin) on the target instance.
- **NetBox service-account token scope** (write limited to the VM custom field + journal entries, not global admin) still needs to be provisioned/confirmed — the app has no way to enforce this itself, it's purely about how the token handed to `NETBOX_TOKEN` is scoped on the NetBox side.
- `scripts/seed_netbox.py`'s `ensure_owner_custom_field` guesses the custom-field creation payload key as `object_types` (NetBox 4.x naming) rather than the older `content_types` — unverified against a live instance. If it's wrong, the script raises with the exact manual-creation steps rather than failing silently; running it once against the test instance will settle this for good.
- No Doctrine-style migrations for the SQLite schema — `app/db.py` just does `CREATE TABLE IF NOT EXISTS` on startup. Fine for the current single-table schema; revisit if it grows.
- `update_vm_recertification` in `app/netbox_real.py` writes `vm_rezert_date` as `datetime.now(UTC).isoformat()` (e.g. `2026-07-08T10:31:31.769558+00:00`). Unverified whether NetBox's datetime custom field accepts this exact format on v4.2.9, or expects e.g. a plain date or a `Z`-suffixed string instead of `+00:00`. The user is creating `vm_still_in_use`/`vm_comment`/`vm_rezert_date` manually rather than via `seed_netbox.py`, so this hasn't been exercised against a real instance yet either.

## Explicitly Out of Scope for v1

No login/SSO, no approval workflow, and no restriction of selectable target contacts to a team/area. The tool still doesn't handle other object types (physical devices, clusters, etc.) — only VMs.

**Multi-VM bulk reassignment is implemented** (per `Anforderungsdokument_multiedit.md`, extending the original spec's v1 non-goal): checkboxes + a single shared owner-picker in `vm_list.html`/`app.js` let a user select many rows and assign them to one new owner at once. This is purely a client-side convenience layer — it fills in the same `owner_<vm_id>` hidden fields the existing per-row picker uses, so `/confirm` and `/save` needed zero changes; they already supported an arbitrary number of simultaneous owner changes. The per-row single-edit picker still works independently and always wins if used after a bulk-apply on the same row (last action wins). The confirm page still lists every changed VM individually, even for a large batch — deliberately not collapsed into a summary count, to keep the audit-relevant "Server X: A → B" visibility FA-4 asks for.

**A first slice of full recertification is implemented** (per `Anforderungsdokument_rezert.md`): storing `vm_still_in_use` (tri-state, never a plain checkbox — see below), `vm_comment`, and `vm_rezert_date` per VM, in a completely separate table/form/endpoint (`/recertify`) from owner reassignment. This is *not* the full recertification workflow the original spec's §8 described as a "separate, larger scope" (no approval/sign-off flow, no gating) — it's just structured storage of the three fields, same minimal spirit as the owner tool itself.

## Security Posture (conscious trade-off, spec §6)

No auth + direct write + free contact choice means *anyone with the link can reassign any VM to any contact, effective immediately in the production CMDB.* This is an accepted trade-off for simplicity, not a technical necessity. The four mitigations that must stay intact **for owner reassignment**: non-derivable token (`uuid4().hex`, mapped server-side — never a reversible encryption of the contact ID), the confirmation dialog before write, the full NetBox journal audit trail, and distributing tokens only over a trusted internal channel (work email via the `tokens.csv` from `generate_tokens.py`, not a shared document). If usage widens beyond the recertification circle, add lightweight SSO (e.g. Azure AD).

**Recertification (`vm_still_in_use`/`vm_comment`/`vm_rezert_date`) still skips the confirmation dialog** owner reassignment gets — that part of the asymmetry was an explicit choice (asked and confirmed, not assumed): the risk profile of marking a VM's recert status is judged lower than reassigning ownership (no orphaned-VM/wrong-owner blast radius, trivially correctable by resubmitting), so the extra review-before-write step wasn't wanted. It **does** write a NetBox journal entry per VM (`"Rezertifizierung durchgeführt durch Rezertifizierungstool (ausgelöst über Link von {Contact}): noch benötigt = Ja/Nein[, Kommentar: '...']."`) — added after initially being skipped, once the audit-trail gap was flagged. If the no-confirmation-dialog choice is ever revisited too, `save_recertification` in `app/routers/owner.py` already mirrors `save_changes`'s per-VM try/except + journal structure closely enough that adding a `/recertify/confirm` interstitial would be a small, mechanical change.

## Language Convention

All requirements, UI text, and domain terminology are in **German** (e.g. `Productowner`, `Rezertifizierung`, `Bereichsleiter`). Keep user-facing text (templates, CLI script output) German; code/comments/identifiers stay in English per this workspace's usual split between DDD-heavy PHP projects (German domain terms) and infra/tooling code.
