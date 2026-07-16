# 02 — Robuste Fehlerbehandlung: keine 500er, keine Interna-Leaks

**Schweregrad: MITTEL** · Aufwand: klein · Abhängigkeiten: teilt die Datei
`app/routers/owner.py` mit Dokument 01 — idealerweise zusammen umsetzen.

Bündelt drei Befunde (M1, M4, M3), die alle die Fehlerpfade der Router betreffen.

---

## Problem

### M1 — Ungefangene `int()`-Konvertierung → 500 statt Fehlerseite
Nur `NetboxError` wird gefangen; ein nicht-numerischer Wert löst `ValueError` aus → roher
500 Internal Server Error statt der freundlichen `error.html`.

- `app/routers/owner.py:119-120` — `int(key.removeprefix("owner_"))` / `int(value)` in
  `/confirm`. POST `owner_abc=1` oder `owner_5=xyz` crasht.
- `app/routers/owner.py:186` — `int(old_contact_id[i])` in `/save`.
- `app/routers/owner.py:236` — `int(key.removeprefix("recert_"))` in `/recertify`.

### M4 — NetBox-Aufrufe außerhalb try/except → 500 bei NetBox-Ausfall
Anders als `show_vm_list` (`:71-81`, sauber gekapselt) liegen diese Aufrufe ungeschützt:

- `app/routers/owner.py:178` — `client.get_contact(contact_id)` in `/save`, **vor** jeder
  Schreiboperation. NetBox down → 500 (immerhin ohne Schreibschaden, aber hässlich).
- `app/routers/owner.py:153` — `_render_vm_list(...)` in `/confirm` (No-Op-Zweig).
- `app/routers/owner.py:239` — `_render_vm_list(...)` in `/recertify` (No-Op-Zweig).
  `_render_vm_list` selbst (`:49-50`) ruft `get_contact` + `list_vms_by_owner` ungeschützt.

### M3 — Fehlermeldungen leaken NetBox-Interna an den Endnutzer
Die rohe `NetboxError` (die den `pynetbox.RequestError` mit Request-URL, internem Hostnamen,
Feldnamen und Response-Body einbettet, siehe `app/netbox_real.py:51-131`) wird 1:1 ausgegeben:

- `app/routers/owner.py:79` — `f"... {exc}. ..."` im HTML.
- `app/routers/owner.py:100` — `JSONResponse({"error": str(exc)}, ...)`.
- `app/routers/owner.py:148` — `f"... {exc}. ..."` im HTML.

---

## Soll-Verhalten

- Ungültige/nicht-numerische Feld-Keys oder -Werte werden **übersprungen** (wie schon bei
  unbekannten Contacts/VMs), nicht als Crash behandelt. Ist danach nichts Sinnvolles übrig,
  greift der bestehende „Keine Änderungen ausgewählt"-Pfad.
- Jeder NetBox-Aufruf in einer Route liegt innerhalb eines try/except, das eine 502-
  `error.html` (bzw. 502-JSON bei `/contacts/search`) liefert — Parität zu `show_vm_list`.
- Nutzer-sichtbare Meldungen sind **generisch** („NetBox ist derzeit nicht erreichbar, bitte
  später erneut versuchen"). Das technische Detail (`exc`) bleibt im Server-Log
  (`logger.error`, bereits vorhanden).

---

## Umsetzung

In `app/routers/owner.py`:

1. **M1:** In den Schleifen von `/confirm` (`:116`) und `/recertify` (`:233`) den `int()`-Cast
   in ein `try/except (ValueError)` mit `continue` fassen. In `/save` entfällt das Problem,
   wenn Dokument 01 umgesetzt wird (kein `int(old_contact_id[i])` mehr) — andernfalls hier
   ebenfalls absichern.
2. **M4:** `/save` komplett (ab `get_contact` `:178`) und die `_render_vm_list`-Aufrufe in
   `/confirm` (`:153`) und `/recertify` (`:239`) in try/except `NetboxError` kapseln, das
   `_error_page(request, 502, "NetBox nicht erreichbar", <generisch>, retry_url=f"/r/{token}")`
   zurückgibt. Muster steht in `:73-81`.
3. **M3:** In den drei Leak-Stellen (`:79`, `:100`, `:148`) `{exc}` aus der Nutzermeldung
   entfernen; `logger.error("... %s", exc)` bleibt. Eine kurze Konstante für die generische
   Meldung reicht.

---

## Test

`tests/test_error_paths.py` (existiert bereits, uncommitted) erweitern. Der `MockNetboxClient`
kann für Fehlerfälle so präpariert werden, dass Methoden `NetboxError` werfen (Monkeypatch /
Subclass). Fälle:

- POST `/confirm` mit `owner_abc=1` → 200 mit „Keine Änderungen", kein 500.
- POST `/recertify` mit `recert_xyz=ja` → kein 500.
- `/save` und `/confirm` mit einem Client, der `get_contact`/`list_vms_by_owner` wirft →
  502-`error.html`, kein 500.
- `/contacts/search` mit werfendem Client → 502-JSON ohne Interna.
- Assertion, dass die gerenderte Fehlermeldung **nicht** den rohen `exc`-Text enthält.

`make test`, `make lint`, `make typecheck` grün.

---

## Definition of Done

- [ ] Kein manipulierbarer POST-Payload erzeugt mehr einen 500 (nur 400/200/502).
- [ ] Alle NetBox-Aufrufe in Routen sind in try/except gekapselt und liefern 502-Fehlerseiten.
- [ ] Nutzer-sichtbare Fehlermeldungen enthalten keine NetBox-Interna; Details nur im Log.
- [ ] Tests decken ValueError-Pfade und NetBox-Ausfall pro Route ab; Suite grün.
