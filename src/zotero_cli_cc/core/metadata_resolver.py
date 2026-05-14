"""DOI → Zotero metadata resolution via Crossref.

The Zotero Web API's `create_items` endpoint does not auto-resolve DOIs into
full metadata (that is done by Zotero desktop's translator). When `zot add
--doi` posts a bare item, the result is an empty entry with only the DOI
field set. This module fills that gap by fetching the Crossref record for a
DOI and mapping it into the Zotero `journalArticle` field set, so the item
created by the API already has title/creators/journal/etc. populated.

Crossref is free, requires no key, and supports a "polite pool" for clients
that identify themselves via the User-Agent. Set `ZOT_CROSSREF_MAILTO` in
your environment to be routed into the polite pool.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

CROSSREF_API_BASE = "https://api.crossref.org/works"
REQUEST_TIMEOUT = 15.0
USER_AGENT_BASE = "zotero-cli-cc (https://github.com/Agents365-ai/zotero-cli-cc)"


class MetadataResolveError(Exception):
    """Raised when Crossref cannot be reached or returns an unparseable response.

    A 404 (DOI unknown to Crossref) is NOT an error — callers receive None.
    """


def _user_agent() -> str:
    mailto = os.environ.get("ZOT_CROSSREF_MAILTO", "").strip()
    if mailto:
        return f"{USER_AGENT_BASE} (mailto:{mailto})"
    return USER_AGENT_BASE


_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _strip_jats(text: str) -> str:
    """Crossref abstracts often arrive as JATS XML — flatten to plain text."""
    cleaned = _JATS_TAG_RE.sub("", text)
    # Collapse whitespace runs introduced by stripped tags.
    return re.sub(r"\s+", " ", cleaned).strip()


def _format_date(date_parts: list[list[int]] | None) -> str | None:
    """Crossref date-parts → ISO-ish string Zotero accepts (YYYY, YYYY-MM, YYYY-MM-DD)."""
    if not date_parts:
        return None
    parts = date_parts[0] if isinstance(date_parts[0], list) else date_parts
    if not parts:
        return None
    return "-".join(f"{int(p):02d}" if i > 0 else str(int(p)) for i, p in enumerate(parts))


def _map_creators(authors: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not authors:
        return []
    creators: list[dict[str, str]] = []
    for a in authors:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if family or given:
            creators.append({"creatorType": "author", "firstName": given, "lastName": family})
            continue
        name = (a.get("name") or "").strip()
        if name:
            # Corporate / single-name authors (e.g. consortia).
            creators.append({"creatorType": "author", "name": name})
    return creators


def _first_str(value: Any) -> str | None:
    """Crossref string fields are typically arrays-of-one — return the first non-empty entry."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def map_crossref_to_zotero(message: dict[str, Any]) -> dict[str, Any]:
    """Map a Crossref `message` object into a Zotero `journalArticle` field dict.

    Only fields actually present in Crossref are emitted, so callers can
    safely merge the result over a Zotero item template without overwriting
    template defaults with empty strings.
    """
    fields: dict[str, Any] = {}

    title = _first_str(message.get("title"))
    if title:
        fields["title"] = title

    creators = _map_creators(message.get("author"))
    if creators:
        fields["creators"] = creators

    container = _first_str(message.get("container-title"))
    if container:
        fields["publicationTitle"] = container

    short_container = _first_str(message.get("short-container-title"))
    if short_container and short_container != container:
        fields["journalAbbreviation"] = short_container

    for crossref_key, zotero_key in (("volume", "volume"), ("issue", "issue"), ("page", "pages")):
        val = message.get(crossref_key)
        if isinstance(val, str) and val.strip():
            fields[zotero_key] = val.strip()

    # Prefer print > online > issued for the canonical publication date.
    date = (
        _format_date(message.get("published-print", {}).get("date-parts"))
        or _format_date(message.get("published-online", {}).get("date-parts"))
        or _format_date(message.get("issued", {}).get("date-parts"))
    )
    if date:
        fields["date"] = date

    issn = _first_str(message.get("ISSN"))
    if issn:
        fields["ISSN"] = issn

    publisher = _first_str(message.get("publisher"))
    if publisher:
        fields["publisher"] = publisher

    language = _first_str(message.get("language"))
    if language:
        fields["language"] = language

    abstract = message.get("abstract")
    if isinstance(abstract, str) and abstract.strip():
        fields["abstractNote"] = _strip_jats(abstract)

    url = _first_str(message.get("URL"))
    if url:
        fields["url"] = url

    doi = _first_str(message.get("DOI"))
    if doi:
        fields["DOI"] = doi

    return fields


def resolve_doi(doi: str, *, timeout: float = REQUEST_TIMEOUT) -> dict[str, Any] | None:
    """Look up a DOI in Crossref and return Zotero-shaped metadata.

    Returns:
        - dict of Zotero `journalArticle` fields (title, creators, ...) on success.
        - None if Crossref returns 404 (DOI genuinely unknown).

    Raises:
        MetadataResolveError on network failure, timeout, 5xx, malformed JSON,
        or any other unexpected response. Callers should treat this as
        "metadata could not be fetched — fall back to a bare item".
    """
    doi = doi.strip()
    if not doi:
        raise MetadataResolveError("Empty DOI")

    url = f"{CROSSREF_API_BASE}/{doi}"
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as e:
        raise MetadataResolveError(f"Crossref request failed: {e}") from e

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise MetadataResolveError(f"Crossref returned HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as e:
        raise MetadataResolveError(f"Crossref returned invalid JSON: {e}") from e

    message = payload.get("message")
    if not isinstance(message, dict):
        raise MetadataResolveError("Crossref response missing 'message' object")
    return map_crossref_to_zotero(message)
