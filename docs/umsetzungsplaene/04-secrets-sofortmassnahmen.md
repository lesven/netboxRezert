# 04 — Secrets: Sofortmaßnahmen

**Schweregrad: HOCH** · Aufwand: klein · Abhängigkeiten: keine · **Keine Code-Änderung** —
Checkliste für Betrieb/Owner. Sollte zuerst erledigt werden.

---

## Problem

### Produktiver NetBox-Schreib-Token liegt im Klartext in `.env`
`/home/svenheising/netbox/owner/.env` enthält einen realen Schreib-Token, `NETBOX_MOCK=false`
und zeigt auf eine erreichbare, nicht-Mock-Instanz. `.env` ist korrekt in `.gitignore`
(`.gitignore:4`) und **nicht** eingecheckt — das Secret ist also nicht im Repo, liegt aber
ungeschützt auf der Platte. Wer Datei-/Backup-Zugriff bekommt, hat direkten Schreibzugriff
auf die Produktiv-CMDB.

> **Der Token ist im Rahmen dieser Schwachstellenprüfung sichtbar geworden und muss als
> kompromittiert gelten.**

### `tokens.csv` mit allen Zugangs-Links liegt real im Arbeitsverzeichnis
`/home/svenheising/netbox/owner/tokens.csv` (52 Datenzeilen) enthält je Contact den
kompletten Zugangs-Link inkl. Token. Tokens sind laut Design die **einzige** Authentifizierung,
permanent gültig, ohne Revoke. Gitignored (gut), aber physisch unverschlüsselt vorhanden.
Jeder mit Lesezugriff kann jede VM-Ownership in Produktion umschreiben.

### Fehlende `.dockerignore` → Secrets im Build-Kontext
Es gibt keine `.dockerignore`. Das Dockerfile kopiert zwar explizit nur `app` und `scripts`
(Secrets landen also **nicht** im Image — gut), aber ohne `.dockerignore` werden `.env`,
`tokens.csv`, `.coverage`, `data/` und Caches als Build-Kontext an den Docker-Daemon gesendet.

### `.coverage` nicht in `.gitignore`
`/home/svenheising/netbox/owner/.coverage` ist untracked, aber nicht ignoriert → kann
versehentlich committet werden. Kosmetisch, aber trivial zu beheben.

---

## Maßnahmen (Reihenfolge einhalten)

1. **Token rotieren — sofort.** In NetBox den aktuellen Service-Account-Token widerrufen und
   einen neuen ausstellen. Dabei den Scope prüfen/setzen: Schreibrecht nur auf das VM-Custom-
   Field + Journal-Einträge, **nicht** global Admin (offener Punkt aus `CLAUDE.md` § Known
   Gaps). Neuen Token nur in die Deployment-Umgebung einspielen (siehe 2), nicht zurück in
   eine Entwickler-`.env` mit Prod-Ziel.
2. **Secret aus der Datei heraus.** Den Token in Produktion über die Umgebung des
   Deployment-Systems / einen Secret-Store bereitstellen (z. B. Docker-/Compose-Secret,
   Umgebungsvariable des Orchestrators), nicht über eine `.env`-Datei auf der Platte.
   Entwickler-Maschinen sollten **keine** `.env` mit Prod-Token + `NETBOX_MOCK=false` halten;
   lokal `NETBOX_MOCK=true` verwenden.
3. **`tokens.csv` behandeln wie ein Passwort-Export.** Nach dem Versand der Links löschen,
   nicht dauerhaft im Arbeitsverzeichnis liegen lassen, nie in ein geteiltes Dokument. Das
   Skript kann sie bei Bedarf idempotent neu erzeugen (`make generate-tokens`, bestehende
   Tokens werden wiederverwendet).
4. **`.dockerignore` anlegen** mit denselben Einträgen wie `.gitignore`, mindestens:
   ```
   .env
   .env.*
   tokens.csv
   .coverage
   data/
   .venv/
   __pycache__/
   .pytest_cache/
   .git/
   ```
5. **`.coverage` in `.gitignore` ergänzen.**

---

## Verifikation

- `git ls-files` zeigt weder `.env`, `tokens.csv`, `.coverage` noch `data/`-Inhalte.
- Der neue Token funktioniert (App startet, VM-Liste lädt gegen die echte Instanz), der alte
  ist widerrufen (Zugriff schlägt fehl).
- `docker build` sendet einen kleineren Kontext (Ausgabe „Sending build context" beobachten)
  und das gebaute Image enthält keine `.env`/`tokens.csv` (`docker run --rm <image> ls -la`).
- `tokens.csv` ist nach Versand nicht mehr im Arbeitsverzeichnis.

---

## Definition of Done

- [ ] Alter Token widerrufen, neuer Token mit minimalem Scope ausgestellt und nur in der
      Deployment-Umgebung hinterlegt.
- [ ] Keine `.env` mit Prod-Token + `NETBOX_MOCK=false` auf Entwickler-Maschinen.
- [ ] `tokens.csv` nach Versand gelöscht; Prozess dafür dokumentiert.
- [ ] `.dockerignore` vorhanden; `.coverage` in `.gitignore`.
