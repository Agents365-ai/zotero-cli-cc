"""Build attachment-rename plans from item metadata.

Pure functions only — no SQLite, no network — so the naming rules and the
main-vs-supplementary classification are unit-testable in isolation. The
physical rename is executed elsewhere (the `zot-cli-bridge` plugin via
`core/local_bridge.rename_attachment`); this module only decides *what* each
attachment should be called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from zotero_cli_cc.models import Attachment, Item

# Tokens a template may reference. Anything else is rejected so a typo surfaces
# as a validation error instead of a literal "{titel}" in a filename.
_KNOWN_TOKENS = frozenset({"journal", "year", "title", "shorttitle", "author"})

# Characters that are illegal in filenames on Windows / unsafe on POSIX.
_ILLEGAL_FS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Filename markers that identify a supplementary / supporting-information PDF.
_SUPP_WORDS = re.compile(r"supp|supporting|appendix|appendices", re.IGNORECASE)
_SUPP_SI = re.compile(r"(?:^|[\W_])si(?:[\W_]|\d|$)", re.IGNORECASE)


class RenameError(Exception):
    """Raised when a rename plan cannot be built (e.g. bad template, no title)."""

    def __init__(self, message: str, *, code: str = "validation_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class RenameEntry:
    attachment_key: str
    old_name: str
    new_name: str
    role: str  # "main" | "supp"
    skip: bool = False  # True when new_name already equals old_name


def is_pdf(att: Attachment) -> bool:
    return att.content_type == "application/pdf" or att.filename.lower().endswith(".pdf")


def is_supplementary(filename: str) -> bool:
    """Heuristic: does this filename look like supplementary material?"""
    return bool(_SUPP_WORDS.search(filename) or _SUPP_SI.search(filename))


def _sanitize(value: str) -> str:
    value = _HTML_TAG.sub("", value)
    value = _ILLEGAL_FS.sub("", value)
    return _WS.sub(" ", value).strip()


def extract_year(item: Item) -> str:
    """First 4-digit year found in the item's date field, else empty."""
    m = re.search(r"\d{4}", item.date or "")
    return m.group(0) if m else ""


def _first_caps_abbrev(name: str) -> str:
    """Abbreviate a venue name to the initials of its significant words.

    Drops lowercase connectives, publisher prefixes (IEEE/ACM), articles, and
    pure numbers — e.g. "IEEE Transactions on Pattern Analysis and Machine
    Intelligence" -> "TPAMI".
    """
    skip = {"IEEE", "ACM", "The"}
    initials = [w[0] for w in name.split() if w and w[0].isupper() and w not in skip and not re.search(r"\d", w)]
    return "".join(initials)


def journal_short(item: Item) -> str:
    """Resolve the `{journal}` token: Jab/# tag > type-aware abbrev > 'Pre'."""
    for tag in item.tags:
        if tag.startswith("Jab/#") and tag[5:]:
            return tag[5:]

    extra = item.extra
    if item.item_type == "journalArticle":
        venue = extra.get("publicationTitle", "")
        if "arxiv" in venue.lower():
            return "Pre"
        return _first_caps_abbrev(venue) or "Pre"
    if item.item_type == "conferencePaper":
        venue = extra.get("conferenceName") or extra.get("proceedingsTitle") or ""
        paren = re.search(r"\(([^)]+)\)", venue)
        if paren:
            return paren.group(1)
        return _first_caps_abbrev(venue) or "Pre"
    if item.item_type == "bookSection":
        book = extra.get("bookTitle", "")
        for marker in ("ECCV", "ACCV"):
            if marker in book:
                return marker
        return _first_caps_abbrev(book) or "Book"
    if item.item_type == "preprint":
        return "Pre"
    return "Pre"


def _tokens(item: Item) -> dict[str, str]:
    short = item.extra.get("shortTitle") or item.title
    author = item.creators[0].last_name if item.creators else ""
    return {
        "journal": journal_short(item),
        "year": extract_year(item),
        "title": _sanitize(item.title),
        "shorttitle": _sanitize(short),
        "author": _sanitize(author),
    }


def resolve_template(template: str, item: Item) -> str:
    """Render a template like '{journal}_{year}_{title}' to a base filename (no extension)."""
    used = set(re.findall(r"\{(\w+)\}", template))
    unknown = used - _KNOWN_TOKENS
    if unknown:
        raise RenameError(
            f"Unknown template token(s): {', '.join('{' + t + '}' for t in sorted(unknown))}. "
            f"Allowed: {', '.join('{' + t + '}' for t in sorted(_KNOWN_TOKENS))}"
        )
    tokens = _tokens(item)
    base = re.sub(r"\{(\w+)\}", lambda m: tokens[m.group(1)], template)
    base = _sanitize(base)
    if not base or base.strip("_-. ") == "":
        raise RenameError("Template produced an empty filename (item is missing title/metadata)")
    return base


def classify_pdfs(attachments: list[Attachment]) -> tuple[Attachment | None, list[Attachment]]:
    """Split PDF attachments into (main, [supplementary...]).

    Main = the first non-supplementary PDF (attachments arrive in dateAdded
    order). If every PDF looks supplementary, the earliest one is promoted to
    main. Extra non-supplementary PDFs beyond the first are treated as
    supplementary so their names never collide.
    """
    pdfs = [a for a in attachments if is_pdf(a)]
    if not pdfs:
        return None, []
    mains = [a for a in pdfs if not is_supplementary(a.filename)]
    supps = [a for a in pdfs if is_supplementary(a.filename)]
    if not mains:
        return pdfs[0], pdfs[1:]
    main = mains[0]
    extra = mains[1:]
    # Keep supps in original (dateAdded) order: merge extras with keyword-supps.
    ordered_supps = [a for a in pdfs if a is not main and (a in extra or a in supps)]
    return main, ordered_supps


def build_plan(
    item: Item,
    attachments: list[Attachment],
    *,
    template: str = "{journal}_{year}_{title}",
    include_supp: bool = True,
) -> list[RenameEntry]:
    """Compute the rename plan for one item's PDF attachments."""
    base = resolve_template(template, item)
    main, supps = classify_pdfs(attachments)
    plan: list[RenameEntry] = []
    if main is not None:
        new_name = f"{base}.pdf"
        plan.append(RenameEntry(main.key, main.filename, new_name, "main", skip=new_name == main.filename))
    if include_supp:
        for i, supp in enumerate(supps):
            suffix = "_SI" if i == 0 else f"_SI{i + 1}"
            new_name = f"{base}{suffix}.pdf"
            plan.append(RenameEntry(supp.key, supp.filename, new_name, "supp", skip=new_name == supp.filename))
    return plan
