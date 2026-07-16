# 05 — Scripts gegen Fehlbedienung absichern

**Schweregrad: MITTEL/HOCH** · Aufwand: klein · Abhängigkeiten: keine.

Betrifft die beiden CLI-Skripte, die außerhalb des normalen App-Flows direkt gegen NetBox
bzw. gegen die Token-DB arbeiten.

---

## Problem

### `seed_netbox.py` — kein echter Schutz gegen die Produktivinstanz  (HOCH)
`scripts/seed_netbox.py:133-134`:
```python
def looks_unconfigured(netbox_url, netbox_token):
    return "example.com" in netbox_url or not netbox_token or netbox_token == "changeme"
```
Der einzige Schutz prüft auf Platzhalter. Eine echte URL besteht die Prüfung problemlos. Das
Skript läuft damit gegen die **Produktivinstanz aus `.env`**:
- `wipe_previous_seed` (`:123-130`) löscht **alle** mit `recert-seed-data` getaggten Objekte
  auf dem Ziel.
- Default `--vm-count 1000` / `--contact-count 50` (`:179-180`) legt massenhaft Objekte an.
- Der interaktive Prompt (`:188-195`) ist die einzige Bremse, und `-y`/`--yes` (`:184`)
  umgeht ihn. Der Docstring behauptet „test instance", nichts erzwingt das.

**Folge:** versehentliches Vollmüllen / Datenverlust in der Produktiv-CMDB.

### `generate_tokens.py` — kann still gegen den Mock laufen  (MITTEL)
`scripts/generate_tokens.py:29` nutzt `get_netbox_client()`, respektiert also `NETBOX_MOCK`.
Bei `NETBOX_MOCK=true` erzeugt es echte, verteilbare Links (`:58`) für die **Mock-Fixture-
Contacts** und schreibt sie ohne jede Warnung nach `tokens.csv` (`:63-68`). Solche Links sind
in Produktion wertlos/falsch. Es fehlt jeder Hinweis, dass Mock aktiv ist.

---

## Soll-Verhalten

- `seed_netbox.py` läuft **nur** gegen eine explizit als Seed-Ziel freigegebene Instanz, nie
  versehentlich gegen Produktion — auch nicht mit `-y`.
- `generate_tokens.py` erzeugt keine Links gegen den Mock, ohne dass der Aufrufer es
  ausdrücklich will.

---

## Umsetzung

### `seed_netbox.py`
1. **Positive Ziel-Freigabe statt Negativ-Platzhalter-Check.** Eine dedizierte
   `SEED_NETBOX_URL` (eigene Env-Variable) einführen; das Skript seedet nur, wenn
   `settings.netbox_url == SEED_NETBOX_URL`. Alternativ eine Allowlist erlaubter Seed-Hosts.
   `looks_unconfigured` (`:133`) bleibt als zusätzliche Bremse.
2. **`-y` erfordert Ziel-Bestätigung.** Auch mit `--yes` den Zielhost prüfen: `--yes` darf
   den interaktiven Prompt (`:188-195`) nur überspringen, wenn das Ziel in der Allowlist steht;
   andernfalls hart abbrechen mit klarer Meldung. So bleibt `-y` für CI gegen die Testinstanz
   nutzbar, kann aber nicht die Produktion treffen.
3. Meldung im Abbruchfall: welcher Host erwartet wurde vs. welcher konfiguriert ist.

### `generate_tokens.py`
4. **Mock-Guard** in `generate_tokens` (`:26-29`): Ist `settings.netbox_mock` gesetzt,
   abbrechen (Exit ≠ 0) oder mindestens laut warnen und eine Bestätigung verlangen — analog
   zur Schutzidee in `seed_netbox`. Damit landen keine Mock-Fixture-Links in `tokens.csv`.

---

## Test

- `tests/test_seed_netbox.py` (existiert, uncommitted): Fall ergänzen, dass `seed`/`main` bei
  einem Ziel außerhalb der Allowlist abbricht — auch mit `-y`.
- `tests/test_generate_tokens.py` (existiert, uncommitted): Fall ergänzen, dass bei
  `NETBOX_MOCK=true` kein CSV geschrieben wird bzw. das Skript abbricht/warnt.
- `make test`, `make lint`, `make typecheck` grün.

---

## Definition of Done

- [ ] `seed_netbox.py` läuft nachweislich nur gegen die freigegebene Seed-Instanz, `-y`
      umgeht diesen Schutz nicht.
- [ ] `generate_tokens.py` schreibt keine Links, wenn `NETBOX_MOCK` aktiv ist (oder verlangt
      explizite Bestätigung).
- [ ] Tests decken beide Abbruch-Pfade ab; Suite grün.
