"""WHOIS/RDAP normalization helpers for Argus."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from typing import Any, Literal

from argus.tools.whois.models import (
    NormalizedDomainRegistration,
    NormalizedIpRegistration,
    NormalizedRegistrationResult,
    RegistrationContact,
    RegistrationRawRefs,
)


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_is_nonempty(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_nonempty(item) for item in value)
    return True


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    return str(value).strip() or None


def _all_texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_all_texts(item))
        return values
    return [str(value).strip()] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _normalize_descriptions(raw: dict[str, Any]) -> list[str]:
    descriptions = _all_texts(raw.get("description"))
    remarks = raw.get("remarks")
    if isinstance(remarks, list):
        for item in remarks:
            if isinstance(item, dict):
                descriptions.extend(_all_texts(item.get("description")))
                descriptions.extend(_all_texts(item.get("title")))
            else:
                descriptions.extend(_all_texts(item))
    return _dedupe(descriptions)


def _normalize_nameservers(value: Any) -> list[str]:
    nameservers: list[str] = []
    if isinstance(value, str):
        return [value.rstrip(".").lower()]
    if isinstance(value, (list, tuple, set)):
        for item in value:
            nameservers.extend(_normalize_nameservers(item))
    elif isinstance(value, dict):
        for key in ("ldhName", "name", "unicodeName"):
            item = _first_text(value.get(key))
            if item:
                nameservers.append(item.rstrip(".").lower())
                break
    return _dedupe(nameservers)


def _normalize_terms_url(raw: dict[str, Any]) -> str | None:
    direct = _first_text(raw.get("terms_of_service_url"))
    if direct:
        return direct
    notices = raw.get("notices")
    if not isinstance(notices, list):
        return None
    for notice in notices:
        if not isinstance(notice, dict):
            continue
        links = notice.get("links")
        if not isinstance(links, list):
            continue
        for link in links:
            if not isinstance(link, dict):
                continue
            href = _first_text(link.get("href"))
            if href:
                return href
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (list, tuple, set)):
        for item in value:
            parsed = _parse_datetime(item)
            if parsed is not None:
                return parsed
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _rir_from_reference(raw: dict[str, Any]) -> str | None:
    candidates = [
        _first_text(raw.get("rir")),
        _first_text(raw.get("port43")),
        _first_text(raw.get("whois_server")),
        _first_text(raw.get("url")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        lowered = candidate.lower()
        if "ripe" in lowered:
            return "RIPE"
        if "arin" in lowered:
            return "ARIN"
        if "apnic" in lowered:
            return "APNIC"
        if "lacnic" in lowered:
            return "LACNIC"
        if "afrinic" in lowered:
            return "AFRINIC"
    return None


def _extract_contact_from_vcard(entity: dict[str, Any]) -> tuple[str | None, str | None]:
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2 or not isinstance(vcard[1], list):
        return None, None

    name: str | None = None
    email: str | None = None
    tel: str | None = None
    for item in vcard[1]:
        if not isinstance(item, list) or len(item) < 4:
            continue
        field = str(item[0]).lower()
        raw_value = item[3]
        value = _first_text(raw_value)
        if not value:
            continue
        if field == "fn":
            name = value
        elif field == "email":
            email = value.removeprefix("mailto:")
        elif field == "tel":
            tel = value.removeprefix("tel:")
    return name, email or tel


def _extract_contacts(
    raw: dict[str, Any],
    role: Literal["abuse", "administrative", "technical", "registrant"],
) -> list[RegistrationContact]:
    contacts: list[RegistrationContact] = []
    for entity in raw.get("entities", []):
        if not isinstance(entity, dict):
            continue
        roles = {str(item).lower() for item in entity.get("roles", []) if isinstance(item, str)}
        if role not in roles:
            continue
        name, fallback = _extract_contact_from_vcard(entity)
        email = _first_text(entity.get("email"))
        tel = _first_text(entity.get("tel"))
        if not email and fallback and "@" in fallback:
            email = fallback
        if not tel and fallback and "@" not in fallback:
            tel = fallback
        contacts.append(
            RegistrationContact(
                role=role,
                name=name or _first_text(entity.get("name")),
                email=email,
                handle=_first_text(entity.get("handle")),
                tel=tel,
                rir=_rir_from_reference(raw),
            )
        )
    return contacts


def _normalize_network(raw: dict[str, Any]) -> str | None:
    cidr_entries = raw.get("cidr0_cidrs")
    if isinstance(cidr_entries, list):
        for item in cidr_entries:
            if not isinstance(item, dict):
                continue
            prefix = _first_text(item.get("v4prefix") or item.get("v6prefix"))
            length = item.get("length")
            if prefix and isinstance(length, int):
                return f"{prefix}/{length}"
    network = _first_text(raw.get("network") or raw.get("cidr"))
    if network:
        return network
    start = _first_text(raw.get("startAddress"))
    end = _first_text(raw.get("endAddress"))
    if not start or not end:
        return None
    try:
        summarized = list(
            ipaddress.summarize_address_range(
                ipaddress.ip_address(start), ipaddress.ip_address(end)
            )
        )
    except ValueError:
        return None
    if summarized:
        return str(summarized[0])
    return None


def normalize_ip_rdap_result(query: str, raw: dict[str, Any]) -> NormalizedRegistrationResult:
    ip_registration = NormalizedIpRegistration(
        queried_ip=query,
        network=_normalize_network(raw),
        ip_version=4 if ":" not in query else 6,
        country=_first_text(raw.get("country")),
        rir=_rir_from_reference(raw),
        name=_first_text(raw.get("name")),
        description=_normalize_descriptions(raw),
        assignment_type=_first_text(raw.get("type")),
        handle=_first_text(raw.get("handle")),
        parent_handle=_first_text(raw.get("parentHandle")),
        registration_date=_parse_datetime(raw.get("registrationDate") or raw.get("eventDate")),
        last_changed_date=_parse_datetime(raw.get("lastChangedDate") or raw.get("updated")),
        expiration_date=_parse_datetime(raw.get("expirationDate")),
        abuse_contacts=_extract_contacts(raw, "abuse"),
        admin_contacts=_extract_contacts(raw, "administrative"),
        technical_contacts=_extract_contacts(raw, "technical"),
        registrant_contacts=_extract_contacts(raw, "registrant"),
    )

    raw_refs = RegistrationRawRefs(
        rdap_url=_first_text(raw.get("url")),
        whois_server=_first_text(raw.get("whois_server") or raw.get("port43")),
        terms_of_service_url=_normalize_terms_url(raw),
    )

    return NormalizedRegistrationResult(
        query=query,
        query_type="ip",
        source="rdap",
        ip_network=ip_registration,
        raw_refs=raw_refs,
    )


def normalize_domain_registration_result(
    query: str,
    raw: dict[str, Any] | str,
    source: Literal["whois", "rdap"],
) -> NormalizedRegistrationResult:
    data = raw if isinstance(raw, dict) else {"raw_text": raw}

    registration = NormalizedDomainRegistration(
        domain=query,
        registrar=_first_text(data.get("registrar") or data.get("registrar_name")),
        registrar_url=_first_text(data.get("registrar_url") or data.get("url")),
        registrar_abuse_email=_first_text(
            data.get("registrar_abuse_contact_email")
            or data.get("abuse_contact_email")
            or data.get("registrar_abuse_email")
        ),
        registrar_abuse_phone=_first_text(
            data.get("registrar_abuse_contact_phone")
            or data.get("abuse_contact_phone")
            or data.get("registrar_abuse_phone")
        ),
        registrant_name=_first_text(data.get("name") or data.get("registrant_name")),
        registrant_org=_first_text(
            data.get("org") or data.get("organization") or data.get("registrant_org")
        ),
        registrant_email=_first_text(data.get("email") or data.get("registrant_email")),
        registrant_country=_first_text(data.get("country") or data.get("registrant_country")),
        admin_email=_first_text(data.get("admin_email")),
        tech_email=_first_text(data.get("tech_email")),
        nameservers=_normalize_nameservers(data.get("name_servers") or data.get("nameservers")),
        status=_dedupe(_all_texts(data.get("status"))),
        creation_date=_parse_datetime(data.get("creation_date")),
        updated_date=_parse_datetime(data.get("updated_date")),
        expiration_date=_parse_datetime(data.get("expiration_date")),
    )

    raw_refs = RegistrationRawRefs(
        rdap_url=_first_text(data.get("url")) if source == "rdap" else None,
        whois_server=_first_text(data.get("whois_server")),
        terms_of_service_url=_first_text(data.get("terms_of_service_url")),
    )

    return NormalizedRegistrationResult(
        query=query,
        query_type="domain",
        source=source,
        domain=registration,
        raw_refs=raw_refs,
    )


__all__ = [
    "normalize_domain_registration_result",
    "normalize_ip_rdap_result",
]
