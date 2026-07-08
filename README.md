# NetBox Product-Owner-Rezertifizierungstool

Schlankes internes Web-Tool, mit dem ein Bereichsleiter (oder ein anderer
bestehender Product Owner) über einen personalisierten Link seine NetBox-VMs
sieht und pro VM einen präziseren Product Owner auswählen kann. Siehe
`Anforderungsdokument_Netbox-Rezertifizierungstool.md` für die vollständigen
Anforderungen und `CLAUDE.md` für Architektur-/Entscheidungsnotizen.

## Setup

```bash
make install          # legt .venv an, installiert Dependencies
cp .env.example .env  # NETBOX_URL / NETBOX_TOKEN eintragen
```

## Entwicklung (gegen Mock-NetBox, kein echter NetBox nötig)

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8080
python -m scripts.generate_tokens --output tokens.csv   # Test-Links erzeugen
```

`NETBOX_MOCK=true` ist der Default in `app/config.py`, solange keine `.env`
mit `NETBOX_MOCK=false` gesetzt ist. Der Mock enthält ein paar Beispiel-VMs
und -Contacts (`app/netbox_mock.py`), passend zur Bulk-Zuordnungs-Situation
aus dem Anforderungsdokument.

## Tests / Lint / Typecheck

```bash
make test
make lint
make lint-fix
make typecheck
```

## Produktivbetrieb (Docker Compose, gegen echten NetBox)

```bash
cp .env.example .env   # NETBOX_URL, NETBOX_TOKEN, BASE_URL setzen; NETBOX_MOCK=false
make up
make generate-tokens   # Links für alle Contacts mit aktuell zugeordneten VMs
```

Die erzeugte `tokens.csv` enthält je Contact eine fertige URL
(`{BASE_URL}/r/{token}`) — diese Links **nur per dienstlicher Mail einzeln
verteilen**, nicht in einem geteilten Dokument (siehe Sicherheitshinweis in
`CLAUDE.md`). Das Skript ist idempotent: bereits vergebene Tokens werden
wiederverwendet, nicht neu erzeugt.

## Sicherheitsmodell

Es gibt bewusst kein Login. Jeder mit einem gültigen Link kann jede seiner
VMs jedem Contact zuweisen, sofort wirksam in der produktiven CMDB. Die
einzigen Schutzmaßnahmen sind: nicht ableitbare Tokens, ein
Bestätigungsdialog vor dem Schreiben und ein vollständiger Audit-Trail
(NetBox Journal Entries). Details siehe `CLAUDE.md` Abschnitt "Security
Posture".
