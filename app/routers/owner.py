import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.netbox_client import NetboxClient, NetboxError, get_netbox_client
from app.schemas import Contact, OwnerChange, RecertChange, RecertSaveResult, SaveResult

logger = logging.getLogger(__name__)

_NETBOX_UNAVAILABLE_MSG = "NetBox ist derzeit nicht erreichbar. Bitte später erneut versuchen."

router = APIRouter(prefix="/r")
templates = Jinja2Templates(directory="app/templates")


def _format_date_de(value: str | None) -> str:
    """ISO datetime string (as stored by NetBox) -> dd.mm.yyyy, for display only."""
    if not value:
        return "–"
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


templates.env.filters["date_de"] = _format_date_de


def _error_page(
    request: Request, status_code: int, title: str, message: str, retry_url: str | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": title, "message": message, "retry_url": retry_url},
        status_code=status_code,
    )


def _resolve_or_none(token: str) -> int | None:
    return db.resolve_token(token)


def _render_vm_list(
    request: Request, token: str, contact_id: int, client: NetboxClient, info_message: str | None = None
) -> HTMLResponse:
    owner = client.get_contact(contact_id)
    vms = client.list_vms_by_owner(contact_id)
    return templates.TemplateResponse(
        request,
        "vm_list.html",
        {"token": token, "owner": owner, "vms": vms, "info_message": info_message},
    )


@router.get("/{token}", response_class=HTMLResponse)
def show_vm_list(request: Request, token: str):
    contact_id = _resolve_or_none(token)
    if contact_id is None:
        return _error_page(
            request,
            404,
            "Link ungültig",
            "Dieser Link ist unbekannt oder wurde nicht für dich erzeugt. "
            "Bitte wende dich an den Absender des Links.",
        )

    client = get_netbox_client()
    try:
        return _render_vm_list(request, token, contact_id, client)
    except NetboxError as exc:
        logger.error("NetBox-Fehler beim Laden der VM-Liste für Contact %s: %s", contact_id, exc)
        return _error_page(
            request,
            502,
            "NetBox nicht erreichbar",
            _NETBOX_UNAVAILABLE_MSG,
            retry_url=f"/r/{token}",
        )


@router.get("/{token}/contacts/search")
def search_contacts(token: str, q: str = "") -> JSONResponse:
    contact_id = _resolve_or_none(token)
    if contact_id is None:
        return JSONResponse({"error": "invalid token"}, status_code=404)

    from app.config import get_settings

    settings = get_settings()
    client = get_netbox_client()
    try:
        results: list[Contact] = (
            client.search_contacts(q, settings.contact_search_limit) if q.strip() else []
        )
    except NetboxError as exc:
        logger.error("NetBox-Fehler bei Contact-Suche '%s': %s", q, exc)
        return JSONResponse({"error": _NETBOX_UNAVAILABLE_MSG}, status_code=502)

    return JSONResponse({"results": [c.model_dump() for c in results]})


@router.post("/{token}/confirm", response_class=HTMLResponse)
async def confirm_changes(request: Request, token: str):
    contact_id = _resolve_or_none(token)
    if contact_id is None:
        return _error_page(request, 404, "Link ungültig", "Dieser Link ist unbekannt.")

    form = await request.form()
    client = get_netbox_client()

    changes: list[OwnerChange] = []
    try:
        for key, value in form.multi_items():
            if not key.startswith("owner_") or not isinstance(value, str):
                continue
            try:
                vm_id = int(key.removeprefix("owner_"))
                new_contact_id = int(value)
            except ValueError:
                continue  # manipulierter/ungültiger Feld-Key oder -Wert

            current_vm = client.get_vm(vm_id)
            if current_vm is None:
                continue
            if current_vm.owner_contact_id == new_contact_id:
                continue  # unchanged, skip

            new_contact = client.get_contact(new_contact_id)
            if new_contact is None:
                continue  # ignore bogus/unknown target contact

            changes.append(
                OwnerChange(
                    vm_id=vm_id,
                    vm_name=current_vm.name,
                    old_contact_id=current_vm.owner_contact_id,
                    old_contact_name=current_vm.owner_contact_name,
                    new_contact_id=new_contact.id,
                    new_contact_name=new_contact.name,
                )
            )
    except NetboxError as exc:
        logger.error("NetBox-Fehler beim Prüfen der Änderungen: %s", exc)
        return _error_page(
            request,
            502,
            "NetBox nicht erreichbar",
            _NETBOX_UNAVAILABLE_MSG,
            retry_url=f"/r/{token}",
        )

    if not changes:
        try:
            return _render_vm_list(request, token, contact_id, client, "Keine Änderungen ausgewählt.")
        except NetboxError as exc:
            logger.error("NetBox-Fehler beim Rendern der VM-Liste nach /confirm: %s", exc)
            return _error_page(
                request,
                502,
                "NetBox nicht erreichbar",
                _NETBOX_UNAVAILABLE_MSG,
                retry_url=f"/r/{token}",
            )

    return templates.TemplateResponse(
        request,
        "confirm.html",
        {"token": token, "changes": changes},
    )


@router.post("/{token}/save", response_class=HTMLResponse)
async def save_changes(
    request: Request,
    token: str,
    vm_id: list[int] = Form(...),
    vm_name: list[str] = Form(...),
    old_contact_id: list[str] = Form(...),
    old_contact_name: list[str] = Form(...),
    new_contact_id: list[int] = Form(...),
    new_contact_name: list[str] = Form(...),
):
    contact_id = _resolve_or_none(token)
    if contact_id is None:
        return _error_page(request, 404, "Link ungültig", "Dieser Link ist unbekannt.")

    client = get_netbox_client()
    try:
        requester = client.get_contact(contact_id)
    except NetboxError as exc:
        logger.error("NetBox-Fehler beim Laden des Token-Contacts %s: %s", contact_id, exc)
        return _error_page(
            request,
            502,
            "NetBox nicht erreichbar",
            _NETBOX_UNAVAILABLE_MSG,
            retry_url=f"/r/{token}",
        )
    requester_name = requester.name if requester else f"Contact #{contact_id}"

    results: list[SaveResult] = []
    for i in range(len(vm_id)):
        try:
            parsed_old_contact_id = (
                int(old_contact_id[i]) if old_contact_id[i] not in ("", "None") else None
            )
        except ValueError:
            parsed_old_contact_id = None
        change = OwnerChange(
            vm_id=vm_id[i],
            vm_name=vm_name[i],
            old_contact_id=parsed_old_contact_id,
            old_contact_name=old_contact_name[i] or None,
            new_contact_id=new_contact_id[i],
            new_contact_name=new_contact_name[i],
        )
        try:
            client.update_vm_owner(change.vm_id, change.new_contact_id)
        except NetboxError as exc:
            logger.error("Owner-Update für VM %s fehlgeschlagen: %s", change.vm_id, exc)
            results.append(SaveResult(change=change, success=False, error=str(exc)))
            continue

        journal_error = None
        comment = (
            f"Product Owner geändert von {change.old_contact_name or 'unbekannt'} zu "
            f"{change.new_contact_name} durch Rezertifizierungstool "
            f"(ausgelöst über Link von {requester_name})."
        )
        try:
            client.create_journal_entry(change.vm_id, comment)
        except NetboxError as exc:
            logger.error("Journal-Eintrag für VM %s fehlgeschlagen: %s", change.vm_id, exc)
            journal_error = str(exc)

        results.append(SaveResult(change=change, success=True, journal_error=journal_error))

    return templates.TemplateResponse(
        request,
        "result.html",
        {"token": token, "results": results},
    )


@router.post("/{token}/recertify", response_class=HTMLResponse)
async def save_recertification(request: Request, token: str):
    contact_id = _resolve_or_none(token)
    if contact_id is None:
        return _error_page(request, 404, "Link ungültig", "Dieser Link ist unbekannt.")

    form = await request.form()
    client = get_netbox_client()
    rezert_date = datetime.now(UTC).isoformat()

    # Only rows the recertifier actively set to "ja"/"nein" are touched - the
    # default "" (tri-state, not just an unchecked checkbox) means the row
    # was never looked at this round and must be left completely alone.
    touched: list[tuple[int, str]] = []
    for key, value in form.multi_items():
        if not key.startswith("recert_") or not isinstance(value, str) or value not in ("ja", "nein"):
            continue
        try:
            touched.append((int(key.removeprefix("recert_")), value))
        except ValueError:
            continue  # manipulierter/ungültiger Feld-Key

    if not touched:
        try:
            return _render_vm_list(
                request, token, contact_id, client, "Keine Rezertifizierung ausgewählt."
            )
        except NetboxError as exc:
            logger.error("NetBox-Fehler beim Rendern der VM-Liste nach /recertify: %s", exc)
            return _error_page(
                request,
                502,
                "NetBox nicht erreichbar",
                _NETBOX_UNAVAILABLE_MSG,
                retry_url=f"/r/{token}",
            )

    try:
        requester = client.get_contact(contact_id)
    except NetboxError as exc:
        logger.error("NetBox-Fehler beim Laden des Token-Contacts %s: %s", contact_id, exc)
        return _error_page(
            request,
            502,
            "NetBox nicht erreichbar",
            _NETBOX_UNAVAILABLE_MSG,
            retry_url=f"/r/{token}",
        )
    requester_name = requester.name if requester else f"Contact #{contact_id}"

    results: list[RecertSaveResult] = []
    for vm_id, decision in touched:
        still_in_use = decision == "ja"
        comment_raw = form.get(f"comment_{vm_id}", "")
        comment = comment_raw if isinstance(comment_raw, str) else ""
        vm_name = f"VM #{vm_id}"
        try:
            current_vm = client.get_vm(vm_id)
            if current_vm is not None:
                vm_name = current_vm.name
            change = RecertChange(vm_id=vm_id, vm_name=vm_name, still_in_use=still_in_use, comment=comment)
            client.update_vm_recertification(vm_id, still_in_use, comment, rezert_date)
        except NetboxError as exc:
            logger.error("Rezertifizierung für VM %s fehlgeschlagen: %s", vm_id, exc)
            change = RecertChange(vm_id=vm_id, vm_name=vm_name, still_in_use=still_in_use, comment=comment)
            results.append(RecertSaveResult(change=change, success=False, error=str(exc)))
            continue

        journal_error = None
        journal_comment = (
            f"Rezertifizierung durchgeführt durch Rezertifizierungstool "
            f"(ausgelöst über Link von {requester_name}): "
            f"noch benötigt = {'Ja' if still_in_use else 'Nein'}"
            + (f", Kommentar: „{comment}“" if comment else "")
            + "."
        )
        try:
            client.create_journal_entry(vm_id, journal_comment)
        except NetboxError as exc:
            logger.error("Journal-Eintrag für VM %s (Rezertifizierung) fehlgeschlagen: %s", vm_id, exc)
            journal_error = str(exc)

        results.append(RecertSaveResult(change=change, success=True, journal_error=journal_error))

    return templates.TemplateResponse(
        request,
        "recert_result.html",
        {"token": token, "results": results},
    )
