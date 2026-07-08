# Anforderungsdokument: Netbox Product-Owner-Rezertifizierungstool

**Status:** Entwurf
**Autor:** Sven Heising
**Version:** 0.1

---

## 1. Ausgangslage und Ziel

In Netbox sind alle betriebenen virtuellen Maschinen erfasst. Jede VM besitzt ein Custom-Feld `vm_product_owner` (Objektreferenz auf ein Netbox-Contact-Objekt). Aktuell sind größere Servermengen teilweise pauschal einem Bereichsleiter statt dem tatsächlich fachlich Verantwortlichen zugeordnet, da der granulare Owner nicht immer bekannt war.

**Ziel:** Ein schlankes, internes Web-Tool, mit dem ein Bereichsleiter (oder ein anderer bestehender Product Owner) über einen personalisierten Link seine ihm zugeordneten VMs einsehen und pro VM einen neuen, präziseren Product Owner aus den bestehenden Netbox-Contacts auswählen kann – ohne das komplexere Netbox-Interface bedienen zu müssen.

Das Tool ist ein **Umverteilungs-Werkzeug**, kein generisches CMDB-Frontend. Es verändert ausschließlich das Feld `vm_product_owner` auf VM-Objekten.

---

## 2. Scope

### 2.1 In Scope
- Anzeige aller VMs, deren `vm_product_owner` = übergebener Contact ist
- Änderung des `Productowner`-Felds pro VM, Auswahl aus allen in Netbox vorhandenen Contacts
- Direktes Zurückschreiben der Änderung nach Netbox via API
- Protokollierung der Änderung (alt → neu) als Journal-Eintrag/Kommentar direkt am Netbox-Objekt
- Aufruf ausschließlich über einen personalisierten Link (siehe Abschnitt 5)
- Nur für interne Nutzung (kein Internet-Exposure)

### 2.2 Explizit außerhalb Scope (v1)
- Andere Objekttypen (physische Devices, Cluster, etc.) – nicht Teil dieser Version
- Nutzer-Login/SSO – bewusst nicht in v1 (siehe Risikohinweis Abschnitt 6)
- Freigabe-Workflow/Vier-Augen-Prinzip vor dem Schreiben nach Netbox
- Einschränkung der auswählbaren Ziel-Contacts auf Team/Bereich
- Massenbearbeitung mehrerer VMs in einem Schritt (kann als spätere Erweiterung ergänzt werden)

---

## 3. Nutzer und Rollen

Es gibt in v1 nur eine funktionale Rolle: **Product Owner / Bereichsleiter**, identifiziert ausschließlich über den ihm zugestellten Link. Es gibt keine Unterscheidung von Berechtigungsstufen innerhalb des Tools – jeder mit gültigem Link kann alle Funktionen nutzen (siehe Risikohinweis).

---

## 4. Funktionale Anforderungen

### FA-1 – Link-Aufruf und Owner-Identifikation
Der Nutzer ruft eine URL auf, die einen Hash/Token enthält. Das Tool löst daraus die zugehörige Netbox-Contact-ID auf.

- **Frage/offen:** Der Hash muss serverseitig einer festen Contact-ID zugeordnet sein (z. B. über eine Mapping-Tabelle, nicht durch Verschlüsselung der Contact-ID selbst, da sonst aus der Contact-ID-Range der Hash erraten werden könnte). Empfehlung: zufälliges, nicht ableitbares Token (z. B. UUID4 oder 32 Byte Zufallswert), keine reversible Verschlüsselung der Contact-ID.

### FA-2 – Serverliste anzeigen
Nach Auflösung des Tokens zeigt das Tool eine Liste aller VMs, bei denen `vm_product_owner` == aufgelöster Contact ist. Angezeigt werden mindestens:
- VM-Name
- aktueller Product Owner (zur Bestätigung)
- ggf. weitere zur Wiedererkennung hilfreiche Felder (Anzahl CPU Kerne, RAM, festplattengrößen) – 

### FA-3 – Owner pro VM ändern
Pro VM-Zeile: Dropdown/Suchfeld mit allen Netbox-Contacts. Auswahl eines neuen Contacts markiert die Zeile als geändert.

- Contact-Liste sollte durchsuchbar sein (Netbox kann mehrere hundert Contacts enthalten) – Freitext-Suche statt langer Dropdown-Liste.

### FA-4 – Speichern
Über eine Sammel-Speichern-Aktion (oder pro Zeile, TBD Design) werden alle geänderten Zuordnungen per Netbox-API zurückgeschrieben.

- Vor dem Schreiben: Bestätigungsdialog mit Übersicht "Server X: Owner A → Owner B" zur Vermeidung von Fehlklicks (Mindestschutz, da kein Freigabe-Workflow existiert).

### FA-5 – Audit-Trail in Netbox
Jede Änderung erzeugt einen Journal-Eintrag (Netbox Journal Entries API) am jeweiligen VM-Objekt mit Inhalt wie:
`"Product Owner geändert von {alter Contact} zu {neuer Contact} durch Rezertifizierungstool (ausgelöst über Link von {Contact, dessen Token verwendet wurde})"`


---

## 5. Nicht-funktionale Anforderungen

| Kategorie | Anforderung |
|---|---|
| Verfügbarkeit | Nur intern erreichbar, kein Internet-Exposure |
| Performance | Liste auch bei mehreren hundert VMs pro Owner ohne spürbare Verzögerung |
| Netbox-API-Nutzung | Read: VMs + Contacts; Write: Custom Field `Productowner`, Journal Entries |
| Fehlerbehandlung | Klare Fehlermeldung bei ungültigem/abgelaufenem Token, bei Netbox-API-Fehlern kein stiller Datenverlust |
| Token-Gültigkeit | **Offene Frage:** Soll der Link zeitlich befristet sein (z. B. nur für den Rezertifizierungszeitraum gültig) oder dauerhaft nutzbar bleiben? |

---

## 6. Sicherheitsrisiko – bewusst zu entscheiden

Die gewählte Kombination (kein Login, direktes Schreiben, freie Contact-Auswahl) bedeutet:

> **Jeder, der den Link kennt, kann ohne Authentifizierung und ohne Vier-Augen-Prinzip beliebige VMs beliebigen Contacts zuweisen – mit sofortiger Wirkung in der produktiven CMDB.**

Das ist \[Sicher\] ein bewusster Trade-off zugunsten von Einfachheit, keine technische Notwendigkeit. Mindestmaßnahmen, die ich unabhängig vom Login-Verzicht empfehlen würde:

1. Token nicht aus der Contact-ID ableitbar (siehe FA-1)
2. Bestätigungsdialog vor dem Schreiben (siehe FA-4)
3. Vollständiger Audit-Trail (siehe FA-5) – vorhanden
4. Tokens nur über einen vertrauenswürdigen internen Kanal (z. B. Mail an die dienstliche Adresse) verteilen, nicht in einem geteilten Dokument

Falls das Tool über den engen Rezertifizierungskreis hinaus bekannt wird oder Links versehentlich weitergeleitet werden, sollte eine Nachschärfung um ein leichtgewichtiges SSO (z. B. Azure AD, ggf. nur als zusätzliche Bestätigung, Link bleibt Einstiegspunkt) eingeplant werden. Für v1 wie von dir vorgegeben nicht enthalten.

---

## 7. Technische Rahmenbedingungen (Annahmen, bitte bestätigen)

| Punkt | Annahme | Status |
|---|---|---|
| Backend | Python, FastAPI | |
| Frontend | serverseitig gerendert (Jinja2 + HTMX) oder einfaches SPA |  |
| Hosting | Docker Compose | |
| Netbox-API-Zugriff | Service-Account-Token mit Schreibrecht beschränkt auf VM-Custom-Field + Journal Entries (kein globaler Admin-Token) |  |
| Netbox-Version/API | REST API v3.x, Custom Fields + Journal Entries Endpunkte NetBox Community v4.2.9|  |


---

## 8. Nicht-Ziele / Abgrenzung

Das Tool ersetzt nicht die vollständige Rezertifizierung (z. B. Bestätigung "Server wird noch benötigt/ist noch aktiv"), sondern ausschließlich die *Neuzuordnung des Product Owners* als Vorbereitung oder Teilschritt davon. Falls eine vollständige Rezertifizierung (inkl. Bestätigungsvermerk "geprüft am") gewünscht ist, ist das ein separater, größerer Scope und sollte als eigene Anforderung behandelt werden.
