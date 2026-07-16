# 03 — Token-Transport & -Lebenszyklus absichern

**Schweregrad: HOCH** · Aufwand: mittel · Abhängigkeiten: keine (TLS-Teil ist Betrieb/DevOps).

Deckt H3 (Token-Leak im Pfad) plus N2 (fehlende Security-Header) und den fehlenden
TLS-Transport ab.

---

## Problem

### H3 — Permanenter Bearer-Token im URL-Pfad landet in Logs & History
Der Token ist das einzige Credential, laut `CLAUDE.md` **permanent gültig, ohne Revoke/Expiry**
(keine solche Spalte in `app/db.py:7-14`). Er steht im Pfad **jeder** Anfrage
(`GET /r/{token}`, `app/routers/owner.py:58`; POST-Routen analog):

- Der Uvicorn-Access-Log schreibt `GET /r/<token> 200` im Klartext; `logging.basicConfig(
  level=logging.INFO)` (`app/main.py:10`) verstärkt das. Jeder vorgelagerte Reverse-Proxy
  loggt den Pfad ebenso, plus Browser-History.
- Der VM-Link in `app/templates/vm_list.html:67` ist `rel="noopener"`, aber es ist **keine**
  `Referrer-Policy` gesetzt (kein Security-Header in `app/main.py`) — reiner Verlass auf den
  Browser-Default.

**Folge:** Ein Token, der einmal in irgendein Log gerät, gewährt dauerhaft Vollzugriff
(siehe Dokument 01 — mit Fix 01 immerhin nur noch auf die VMs des jeweiligen Contacts). Es
gibt keine Möglichkeit, ihn zu widerrufen.

### N2 — Keine Security-Header
Kein `X-Frame-Options`/`frame-ancestors` (Clickjacking), keine `Referrer-Policy`, keine CSP.
(Klassisches CSRF greift dank Token-in-URL statt Cookie nicht — kein Handlungsbedarf dort.)

### TLS — Token über Klartext-HTTP
Uvicorn bindet direkt auf `0.0.0.0:8000` (`Dockerfile` CMD), via Compose auf einen Host-Port
gemappt — **ohne** TLS-Terminierung. `.env` hat `BASE_URL=http://...`. Der Token im Pfad
wandert damit unverschlüsselt über die Leitung (Netzwerk-Sniffing, Proxy-Logs).

---

## Soll-Verhalten

- Token erscheinen nicht (oder redigiert) in Access-Logs.
- Der Browser sendet den token-tragenden Pfad **nie** als Referer an Dritte.
- Grundlegende Security-Header sind gesetzt.
- Der Token-Pfad wird nur über HTTPS übertragen.
- Optional (Entscheidung des Owners): Tokens sind widerrufbar.

---

## Umsetzung

### Pflicht (App)
1. **Security-Header via Middleware** in `app/main.py` (nach `app = FastAPI(...)`,
   `:19`): eine `@app.middleware("http")`-Funktion, die auf jede Response setzt:
   - `Referrer-Policy: no-referrer`
   - `X-Frame-Options: DENY` (bzw. CSP `frame-ancestors 'none'`)
   - `X-Content-Type-Options: nosniff`
   - eine restriktive `Content-Security-Policy` (die App lädt bewusst keine externen
     Ressourcen — `default-src 'self'` passt, ggf. `'unsafe-inline'` für die kleinen
     Inline-Skripte prüfen).
2. **Access-Log-Redaction:** Den Uvicorn-Access-Logger so konfigurieren, dass `/r/<token>`
   nicht im Klartext erscheint (eigener Log-Filter, der den Token-Teil des Pfads maskiert),
   oder Access-Log in Produktion deaktivieren und Zugriffe auf Proxy-Ebene ohne Pfad loggen.

### Pflicht (Betrieb / DevOps)
3. **TLS-terminierender Reverse-Proxy** (nginx / traefik / caddy) vor die App; Uvicorn nur
   intern erreichbar. `BASE_URL` in `.env` auf `https://<öffentlicher-host>` umstellen (das
   ist zugleich der Wert, der in die verteilten Links geht — siehe Dokument 06 zur
   `localhost`-Inkonsistenz). Reverse-Proxy so konfigurieren, dass er den vollen Pfad
   **nicht** loggt.

### Optional (Produktentscheidung)
4. **Revoke/Expiry:** `app/db.py` `_SCHEMA` (`:7-14`) um `revoked_at`/`expires_at` erweitern;
   `resolve_token` (`:36-42`) liefert `None` für widerrufene/abgelaufene Tokens. Widerspricht
   der aktuellen „permanent"-Entscheidung in `CLAUDE.md` — deshalb bewusst optional und nur
   nach Rücksprache mit dem Owner. Falls umgesetzt: `CLAUDE.md` § „Resolved Decisions"
   aktualisieren.

---

## Test

- Unit/Integration: Response-Header-Assertions (jede Route liefert `Referrer-Policy`,
  `X-Frame-Options`, CSP).
- Log-Redaction: Test, der einen Request absetzt und prüft, dass der Access-Log den Token
  nicht im Klartext enthält.
- Falls Revoke umgesetzt: Test, dass ein widerrufener Token 404 liefert.
- TLS/Proxy: manuell im Staging verifizieren (`curl -v https://...`, Proxy-Access-Log
  sichten).

---

## Definition of Done

- [ ] Alle Responses tragen `Referrer-Policy: no-referrer` + Frame-/Content-Type-Header + CSP.
- [ ] Token erscheinen nicht im Klartext im Access-Log.
- [ ] Produktion ist nur über HTTPS erreichbar; `BASE_URL` ist HTTPS + öffentlicher Host.
- [ ] (Falls gewählt) Revoke/Expiry implementiert und in `CLAUDE.md` dokumentiert.
