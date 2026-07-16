# 07 — Verifizierung gegen eine echte NetBox v4.2.9

**Schweregrad: HOCH (Restrisiko-Gate vor Go-Live)** · Aufwand: mittel · Abhängigkeiten:
braucht eine erreichbare Test-NetBox-Instanz (nicht Produktion).

Kein Bugfix, sondern das Schließen der eigentlichen Testlücke: `app/netbox_real.py` ist der
**einzige** Code mit echtem I/O, wird aber ausschließlich gegen Fakes getestet
(`tests/test_netbox_real.py` ersetzt `client._api` durch `SimpleNamespace`) und lief laut
`CLAUDE.md` § Known Gaps **noch nie** gegen eine echte NetBox. Die 99 % Coverage sagt darüber
nichts aus — sie misst ausgeführte Zeilen, nicht die realen API-Annahmen.

---

## Die vier unverifizierten Annahmen

1. **Filter-Syntax `cf_vm_product_owner=<id>`** für ein Objekt-Typ-Custom-Field. `netbox_real.py`
   filtert VMs server-seitig danach und prüft client-seitig nach (belt-and-braces). Ob NetBox
   v4.2.9 diese Filter-Semantik so unterstützt, ist ungeprüft.
2. **Custom-Field-JSON-Form.** `_to_vm` (`app/netbox_real.py:28-30`) liest
   `record.custom_fields.get("vm_product_owner")` und erwartet ein Nested-Objekt mit
   `id`/`display`. Ob die reale API genau diese Form liefert, ist ungeprüft.
3. **Custom-Field-Anlage-Payload:** `object_types` (NetBox 4.x) vs. `content_types` (älter).
   `scripts/seed_netbox.py` `ensure_owner_custom_field` rät `object_types` — unverifiziert.
4. **Datumsformat für `vm_rezert_date`.** `/recertify` schreibt
   `datetime.now(UTC).isoformat()` (z. B. `2026-07-08T10:31:31.769558+00:00`,
   `app/routers/owner.py:227`). Ob NetBox das exakte Format für ein Datetime-Custom-Field
   akzeptiert (oder ein `Z`-Suffix / reines Datum erwartet), ist ungeprüft.

Zusätzlich zu bestätigen (aus `CLAUDE.md` § Known Gaps): dass die Contacts unter
`tenancy.contacts` liegen (nicht in einem separaten Plugin), und dass der Service-Account-
Token nur auf das VM-Custom-Field + Journal-Einträge schreiben darf (Scope, siehe Dokument 04).

---

## Umsetzung

Ein reproduzierbares Smoke-Test-Skript (z. B. `scripts/smoke_real_netbox.py`) **oder** eine
Checkliste, die gegen eine Test-NetBox v4.2.9 folgende Schritte durchführt und protokolliert:

1. `seed_netbox.py` einmal gegen die Testinstanz laufen lassen (mit dem Schutz aus Dokument
   05). Verifiziert Annahme 3 (Custom-Field-Anlage) direkt — schlägt sie fehl, nennt das
   Skript laut `CLAUDE.md` bereits die manuellen Schritte.
2. Über `RestNetboxClient` (nicht Mock, `NETBOX_MOCK=false`) je einmal:
   - `list_vms_with_owner()` und `list_vms_by_owner(<id>)` → prüft Annahme 1 (Filter) und
     Annahme 2 (Nested-Objekt-Parsing in `_to_vm`). Erwartetes vs. tatsächliches Ergebnis
     protokollieren.
   - `get_vm(<id>)` → Felder gegen `Vm`-Schema abgleichen.
   - `update_vm_owner(<id>, <contact>)` gefolgt von `get_vm` → Änderung sichtbar?
   - `create_journal_entry(<id>, "...")` → Eintrag in NetBox vorhanden?
   - `update_vm_recertification(<id>, True, "test", <isoformat-datum>)` → prüft Annahme 4
     (Datumsformat). Bei Ablehnung die akzeptierten Formate notieren und `netbox_real.py`
     entsprechend anpassen.
3. Contacts-Endpoint bestätigen: `nb.tenancy.contacts.get(...)` liefert Daten.
4. Token-Scope negativ prüfen: mit dem Service-Token einen **nicht** erlaubten Schreibzugriff
   (z. B. ein anderes Objekt/Feld) versuchen → muss abgelehnt werden.

Alle Abweichungen führen zu einem gezielten Fix in `app/netbox_real.py` bzw.
`scripts/seed_netbox.py` und einer Aktualisierung von `CLAUDE.md` § Known Gaps (Punkte
abhaken).

> Nutzt ausschließlich synthetische Testdaten (Seed-Tag `recert-seed-data`), niemals echte
> Objekte der Produktivinstanz.

---

## Definition of Done

- [ ] Alle vier Annahmen sind gegen v4.2.9 verifiziert oder der Code ist an das reale
      Verhalten angepasst.
- [ ] `tenancy.contacts`-Endpoint und Token-Scope bestätigt.
- [ ] Das Smoke-Skript/Protokoll ist reproduzierbar abgelegt (für künftige NetBox-Upgrades).
- [ ] `CLAUDE.md` § Known Gaps ist entsprechend aktualisiert (verifizierte Punkte entfernt).
