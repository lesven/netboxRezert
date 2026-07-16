# 06 — Deployment-Härtung

**Schweregrad: MITTEL** · Aufwand: mittel · Abhängigkeiten: keine (überschneidet sich beim
Reverse-Proxy mit Dokument 03).

Sammelbecken für Betriebs-/Robustheits-Schwächen, die einzeln klein sind, in Summe aber den
Produktivbetrieb absichern.

---

## Problem & Umsetzung

### 1. Container läuft als root  (MITTEL)
`Dockerfile` hat kein `USER`-Directive → Uvicorn läuft als root im Container.
**Fix:** Non-Root-User anlegen und setzen, `data/`-Ownership anpassen. Nach `RUN mkdir -p
/app/data` (`Dockerfile:11`):
```dockerfile
RUN adduser --system --no-create-home appuser && chown -R appuser /app/data
USER appuser
```

### 2. Kein NetBox-Request-Timeout  (MITTEL)
`app/netbox_real.py:22` — `pynetbox.api(url, token=token)`. pynetbox/requests hat per Default
**kein** Timeout; eine hängende NetBox blockiert den Worker unbegrenzt.
**Fix:** eine `requests.Session` mit gesetztem Timeout an pynetbox übergeben (z. B. via
`self._api.http_session` mit einem Adapter/Timeout-Wrapper) oder Timeout global setzen.
Timeout als Setting in `app/config.py` konfigurierbar machen.

### 3. Kein Healthcheck  (MITTEL)
`app/main.py:25-27` bietet `/healthz`, aber `docker-compose.yml` nutzt es nicht;
`restart: unless-stopped` (`:14`) startet nur bei Prozess-Crash neu, nicht bei „App hängt".
**Fix:** `healthcheck`-Block im Compose-`app`-Service:
```yaml
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### 4. `/contacts/search` ungedrosselt + gibt E-Mails aus  (MITTEL — M5)
`app/routers/owner.py:84-102` hat kein Rate-Limit und reicht Queries direkt an NetBox durch;
`Contact.model_dump()` (`:102`) liefert auch `email`. Mit einem Token lässt sich so das
Kontaktverzeichnis inkl. E-Mails enumerieren und NetBox-Last ungedrosselt erzeugen.
**Fix:** einfaches Rate-Limit pro Token (z. B. `slowapi` oder ein kleiner In-Memory-Zähler)
und prüfen, ob die E-Mail im Autocomplete-JSON überhaupt gebraucht wird — falls nicht, aus
`app/schemas.py` `Contact.model_dump()`-Ausgabe des Such-Endpoints entfernen.

### 5. SQLite ohne WAL/Timeout; Multi-Worker nicht abgesichert  (NIEDRIG — N1)
`app/db.py:24-33` — `sqlite3.connect(...)` mit Defaults (kein WAL, 5 s Timeout). Die Web-App
liest nur, aber `generate_tokens` schreibt; parallel sind „database is locked"-Fehler möglich.
Der Container startet Uvicorn ohne `--workers` (implizit 1), aber nichts erzwingt das.
**Fix:** in `_connect` `PRAGMA journal_mode=WAL` und ein `busy_timeout` setzen; die
Single-Worker-Annahme im Compose/Dockerfile explizit dokumentieren (oder bewusst auf 1
festnageln), damit Skalierung nicht still die SQLite-Annahme bricht.

### 6. Config-Inkonsistenzen  (NIEDRIG)
- `BASE_URL` steht auf `localhost` (`.env`) — die generierten Links (`generate_tokens.py:58`)
  zeigen dann auf `localhost` und sind per Mail unbrauchbar. Muss der öffentliche HTTPS-Host
  sein (siehe Dokument 03).
- Port-Defaults divergieren: `docker-compose.yml:5` mappt `8084:8000`, `:11` defaultet
  `BASE_URL` auf `:8080`, `app/config.py:15` ebenfalls `:8080`. Vereinheitlichen.
- `NETBOX_MOCK`-Default: `app/config.py:11` = `True`, `docker-compose.yml:9` = `false`.
  Uneinheitlich; einen sicheren Default festlegen und dokumentieren (Mock als Default ist
  ok, muss aber in Produktion sicher auf `false` gesetzt sein).

---

## Test

- Container startet als Non-Root: `docker run --rm <image> id` zeigt nicht `uid=0`.
- Timeout: Integrationstest mit einem Fake, der verzögert/hängt → Aufruf bricht nach Timeout
  mit `NetboxError` ab statt zu blockieren.
- Healthcheck: `docker compose ps` zeigt `healthy`.
- Rate-Limit: Test, dass N+1 Suchanfragen pro Zeitfenster gedrosselt werden.
- SQLite-WAL: `PRAGMA journal_mode` gibt `wal` zurück; paralleler Lese/Schreib-Test ohne
  „database is locked".
- `make test`, `make lint`, `make typecheck` grün.

---

## Definition of Done

- [ ] Container läuft als Non-Root-User.
- [ ] NetBox-Aufrufe haben ein Timeout; hängende NetBox blockiert den Worker nicht.
- [ ] Compose-Healthcheck nutzt `/healthz`.
- [ ] `/contacts/search` ist rate-limited; E-Mail-Ausgabe nur, wenn gebraucht.
- [ ] SQLite nutzt WAL + Busy-Timeout; Worker-Annahme dokumentiert.
- [ ] `BASE_URL`, Ports und `NETBOX_MOCK`-Default sind konsistent und produktionssicher.
