# Umsetzungspläne — Übersicht

Ergebnis einer Schwachstellenprüfung des NetBox-Owner-Rezertifizierungstools
(FastAPI, kein Login, Token-Link in der URL, schreibt direkt in die Produktions-CMDB).

Jedes der folgenden Dokumente ist **in sich abgeschlossen** und kann einzeln in die
Entwicklung gegeben werden. Abhängigkeiten sind jeweils oben im Dokument benannt.

## Was ist Absicht, was ist Bug?

`CLAUDE.md` (§ Security Posture) dokumentiert eine **bewusst akzeptierte** Grundentscheidung:
kein Login, jeder mit dem Link darf umschreiben, Token permanent. Diese Dokumente
kritisieren **nicht** diese Entscheidung — sie beheben Stellen, an denen die App **mehr**
zulässt als die dokumentierte Posture verspricht (z. B. fremde VMs statt nur eigene), oder wo
Robustheit/Betrieb unabhängig von der Auth-Frage brechen.

## Dokumente

| # | Dokument | Thema | Schweregrad | Aufwand | Abhängigkeit |
|---|----------|-------|-------------|---------|--------------|
| 01 | `01-autorisierung-und-save-validierung.md` | Owner-Scoping erzwingen, `/save` neu validieren, Audit-Trail | **HOCH** | M | – |
| 02 | `02-robuste-fehlerbehandlung.md` | 500 → saubere Fehlerseiten, keine Interna-Leaks | MITTEL | S | teilt Datei mit 01 |
| 03 | `03-token-transport-und-lebenszyklus.md` | Token-Leak in Logs, TLS, Security-Header, Revoke | **HOCH** | M | – |
| 04 | `04-secrets-sofortmassnahmen.md` | Token rotieren, `.env`/`tokens.csv`, `.dockerignore` | **HOCH** | S | keine Code-Änderung |
| 05 | `05-script-absicherung.md` | `seed_netbox` Prod-Schutz, `generate_tokens` Mock-Guard | MITTEL/HOCH | S | – |
| 06 | `06-deployment-haertung.md` | Non-Root, Timeout, Healthcheck, Rate-Limit, SQLite | MITTEL | M | – |
| 07 | `07-real-netbox-verifizierung.md` | Smoke-Test gegen echte NetBox v4.2.9 (4 Unbekannte) | **HOCH** | M | vor Go-Live |

## Empfohlene Reihenfolge

1. **04** (Secrets) — sofort, unabhängig, kein Code. Der Prod-Token ist sichtbar geworden.
2. **01 + 02** — zusammen, gleicher Codepfad (`app/routers/owner.py`). Der Kern-Fix.
3. **05** — verhindert versehentliches Vollmüllen/Fehl-Links.
4. **03 + 06** — Transport- und Betriebs-Härtung, vor produktivem Roll-out.
5. **07** — Pflicht-Gate vor dem ersten Lauf gegen die echte NetBox.

## Was die 99 % Testabdeckung nicht zeigt

`app/netbox_real.py` — der einzige Code mit echtem I/O — wird ausschließlich gegen Fakes
getestet und lief laut `CLAUDE.md` noch nie gegen eine echte NetBox. Coverage misst
ausgeführte Zeilen, nicht die realen Integrationspfade. Dokument **07** adressiert genau diese
Lücke.
