# 01 — Owner-Autorisierung erzwingen & `/save` neu validieren

**Schweregrad: HOCH (Kern-Fix)** · Aufwand: mittel · Abhängigkeiten: teilt die Datei
`app/routers/owner.py` mit Dokument 02 — idealerweise zusammen umsetzen.

Dieses Dokument bündelt drei Befunde (H1, H2, M2), weil sie exakt denselben Codepfad
betreffen und ein gemeinsamer Umbau sie alle schließt.

---

## Problem

### H1 — Jeder Token darf jede beliebige VM umschreiben (IDOR)
Die App prüft an **keiner** Stelle, dass eine übermittelte `vm_id` zum Token-Contact gehört.
Der aufgelöste Token-Inhaber (`contact_id`) wird nur für den Journal-Text verwendet, nie zur
Autorisierung.

- `app/routers/owner.py:122` — `/confirm` holt `client.get_vm(vm_id)` für **jede** ID.
- `app/routers/owner.py:192` — `/save` ruft `client.update_vm_owner(vm_id, ...)` ohne
  Owner-Check.
- `app/routers/owner.py:251-255` — `/recertify` schreibt für jede beliebige `vm_id`.

**Folge:** Ein Inhaber *eines* gültigen Tokens kann per handgemachtem POST **jede VM der
gesamten Produktions-CMDB** an jeden beliebigen Contact umschreiben bzw. rezertifizieren.
Ein einziger geleakter Link = Schreibzugriff auf alle VMs, nicht nur die des Opfers. Das
übersteigt die in `CLAUDE.md` dokumentierte „nur eigene VMs"-Erwartung.

### H2 — `/save` re-validiert nichts (Bestätigungsschritt umgehbar, TOCTOU, fälschbarer Audit-Trail)
`/confirm` (`:122-141`) holt jede VM frisch und difft sauber gegen den Ist-Zustand — gut.
Aber `/save` (`:162-216`) vertraut **ausschließlich** den versteckten Formularfeldern:

- Man kann `/confirm` komplett überspringen und direkt an `/save` POSTen → der
  Bestätigungsdialog (eine der vier dokumentierten Kernschutzmaßnahmen) ist wirkungslos.
- **TOCTOU:** Ändert sich der Owner zwischen `/confirm` und `/save`, überschreibt `/save`
  blind — kein erneuter Abgleich.
- `new_contact_id` (`:170`, `:188`) wird in `/save` nicht geprüft (in `/confirm` schon,
  `:128-130`) → nicht existierende Contact-ID als Owner setzbar.
- `old_contact_id`/`old_contact_name` (`:168-169`, `:186-187`) fließen ungeprüft aus dem POST
  in den Journal-Eintrag (`:200-202`) → **Audit-Trail fälschbar** (falscher „von X"-Eintrag).

### M2 — Parallel-Listen-Längen-Mismatch → IndexError/500
Die sechs `Form(...)`-Listen (`:166-171`) werden positionsbasiert gezippt
(`for i in range(len(vm_id))`, `:182`). Ein POST mit z. B. 3× `vm_id` aber 1×
`new_contact_id` löst einen ungefangenen `IndexError` aus → 500.

---

## Soll-Verhalten

- `/confirm`, `/save` und `/recertify` bearbeiten **nur VMs, die aktuell dem Token-Contact
  gehören.** Fremde `vm_id` werden verworfen und als abgelehnte Zeile sichtbar gemacht (nicht
  still gedroppt — Transparenz für den Nutzer und die Audit-Prüfung).
- `/save` leitet den Ist-Zustand (`old_contact_id`, `old_contact_name`) **immer aus einem
  frischen `client.get_vm(vm_id)`** ab, nie aus den Hidden-Feldern. Ziel-`new_contact_id`
  wird via `client.get_contact` verifiziert. No-Op-Zeilen (Owner unverändert) werden gedroppt
  — Parität zu `/confirm`.
- Der positionsbasierte Listen-Zip entfällt; iteriert wird über den re-geholten Ist-Zustand.

---

## Umsetzung

Zentral in `app/routers/owner.py`.

1. **Helper einführen** (Datei-lokal), der aus einer Menge eingereichter `(vm_id, ziel)`
   die autorisierten Änderungen baut — genau die Logik, die `/confirm` heute schon in
   `:116-141` hat, plus die Owner-Zugehörigkeitsprüfung:
   ```python
   current_vm = client.get_vm(vm_id)
   if current_vm is None:
       continue                      # gelöschte VM
   if current_vm.owner_contact_id != contact_id:
       # fremde VM -> abgelehnt, nicht bearbeiten
       rejected.append(vm_id)
       continue
   ```
   Dieselbe Prüfung in `/confirm` und `/save` verwenden.

2. **`/save` umbauen** (`:162-216`): Statt sechs paralleler `Form(...)`-Listen nur die
   `owner_<vm_id>`-Felder aus `await request.form()` lesen (wie `/confirm` in `:116-120`).
   Für jede Zeile `current_vm` frisch holen, Owner-Zugehörigkeit prüfen,
   `old_contact_*` aus `current_vm` nehmen, `new_contact` via `get_contact` verifizieren,
   dann `update_vm_owner` + `create_journal_entry`. Der Journal-Text (`:200-202`) bleibt
   wortgleich, speist sich aber aus den verifizierten Werten. Das löst H2, M2 und die
   Ziel-Validierung in einem Zug.

   > Konsequenz: Die Hidden-Felder in `confirm.html` werden für die Autorisierung nicht mehr
   > gebraucht. Sie können bleiben (Anzeige) oder auf `vm_id` + `new_contact_id` reduziert
   > werden — die Server-Seite verlässt sich nicht mehr darauf.

3. **`/recertify` absichern** (`:245-255`): vor `update_vm_recertification` dieselbe
   Owner-Zugehörigkeitsprüfung über das ohnehin schon geholte `current_vm` (`:251`)
   einziehen; fremde VM → als abgelehnte `RecertSaveResult`-Zeile ausweisen.

4. **Abgelehnte Zeilen darstellen:** `confirm.html` / `result.html` / `recert_result.html`
   um einen Hinweis „nicht bearbeitet (gehört dir nicht mehr / wurde entfernt)" ergänzen.
   `SaveResult`/`RecertSaveResult` in `app/schemas.py` ggf. um ein `rejected`/`reason`-Feld
   erweitern.

---

## Test

`tests/test_confirm_and_save.py` als Muster nutzen (läuft gegen `MockNetboxClient`).
Neue Fälle:

- `/save` mit einer `vm_id`, die einem **anderen** Contact gehört → keine Schreiboperation,
  Zeile als abgelehnt im Ergebnis.
- Direkter POST an `/save` **ohne** vorheriges `/confirm`, mit manipuliertem
  `old_contact_name` → Journal-Eintrag enthält den **echten** alten Owner, nicht den
  eingereichten.
- TOCTOU: Owner wird nach dem Rendern via Mock geändert, dann `/save` → No-Op / neuer
  Ist-Zustand gewinnt, kein blindes Überschreiben.
- Listen-Mismatch bzw. fehlende Felder → 400/Fehlerseite, kein 500.
- `/recertify` mit fremder `vm_id` → abgelehnt.

`make test`, `make lint`, `make typecheck` müssen grün sein.

---

## Definition of Done

- [ ] Keine der drei schreibenden Routen bearbeitet eine VM, die dem Token-Contact nicht
      aktuell gehört.
- [ ] `/save` leitet Ist-Zustand + Ziel ausschließlich aus frischen NetBox-Reads ab; Hidden-
      Felder sind für die Autorisierung irrelevant.
- [ ] Journal-Einträge sind nicht mehr über Client-Input fälschbar.
- [ ] Abgelehnte/übersprungene Zeilen sind für den Nutzer sichtbar.
- [ ] Neue Tests decken fremde VM-IDs, übersprungenes `/confirm` und TOCTOU ab; Suite grün.
