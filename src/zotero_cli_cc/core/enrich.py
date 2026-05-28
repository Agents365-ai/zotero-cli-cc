"""Resolve and merge journal-metric values into an item's Extra field.

Source-neutral by design: the values come from the caller — inline `--set`
pairs or a user-maintained `--from-map` TOML table — never from a bundled
dataset or a third-party API. `zot` provides the *mechanism* (writing labeled
metrics into Zotero's Extra field, the official custom-field channel); the
*data* stays the user's responsibility, so the tool isn't coupled to any
external product.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from zotero_cli_cc.models import Item

# Delimiters for the zot-managed region inside the Extra field. Re-running
# enrich replaces only the text between these markers, leaving any other Extra
# content (DOI:, Citation Key:, tex.ids, etc.) untouched.
BLOCK_START = "<!-- zot:metrics -->"
BLOCK_END = "<!-- /zot:metrics -->"


class EnrichError(Exception):
    """Raised on bad `--set` input or an unreadable `--from-map` file."""

    def __init__(self, message: str, *, code: str = "validation_error") -> None:
        super().__init__(message)
        self.code = code


def parse_set_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """Parse `--set "Label=value"` pairs into an ordered dict."""
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            raise EnrichError(f"--set must be 'key=value', got: {p!r}")
        k, v = p.split("=", 1)
        k = k.strip()
        if not k:
            raise EnrichError(f"--set has an empty key: {p!r}")
        out[k] = v.strip()
    return out


def load_journal_map(path: Path) -> dict[str, dict[str, str]]:
    """Load a TOML table of `journal name -> {metric: value}`.

    Keys are lower-cased for case-insensitive journal lookup. Example file:

        ["Bioinformatics"]
        "SCI IF" = "5.8"
        "JCR" = "Q1"
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise EnrichError(f"Cannot read journal map {path}: {e}") from e
    out: dict[str, dict[str, str]] = {}
    for journal, metrics in data.items():
        if isinstance(metrics, dict):
            out[journal.strip().lower()] = {str(k): str(v) for k, v in metrics.items()}
    return out


def journal_of(item: Item) -> str:
    """The journal/venue name used to look an item up in a `--from-map` table."""
    if item.item_type == "conferencePaper":
        return item.extra.get("conferenceName") or item.extra.get("proceedingsTitle") or ""
    return item.extra.get("publicationTitle", "")


def metrics_for(item: Item, journal_map: dict[str, dict[str, str]], set_pairs: dict[str, str]) -> dict[str, str]:
    """Resolve the metrics to write for one item: map lookup, then `--set` overrides."""
    metrics: dict[str, str] = {}
    if journal_map:
        name = journal_of(item).strip().lower()
        if name and name in journal_map:
            metrics.update(journal_map[name])
    metrics.update(set_pairs)
    return metrics


def merge_extra(existing: str, metrics: dict[str, str]) -> str:
    """Insert/replace the zot-managed metrics block in an Extra field value."""
    block = "\n".join([BLOCK_START, *(f"{k}: {v}" for k, v in metrics.items()), BLOCK_END])
    existing = existing or ""
    if BLOCK_START in existing and BLOCK_END in existing:
        before = existing.split(BLOCK_START, 1)[0].rstrip("\n")
        after = existing.split(BLOCK_END, 1)[1].lstrip("\n")
        base = "\n".join(p for p in (before, after) if p)
    else:
        base = existing.rstrip("\n")
    return f"{base}\n{block}" if base else block
