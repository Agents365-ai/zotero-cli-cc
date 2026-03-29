"""Semantic Scholar API client for checking preprint publication status."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

API_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "externalIds,journal,venue,publicationDate,title,publicationVenue"

# Rate limits
RATE_DELAY_NO_KEY = 3.0  # seconds between requests without API key
RATE_DELAY_WITH_KEY = 1.0  # seconds between requests with API key
REQUEST_TIMEOUT = 15.0

# bioRxiv/medRxiv DOI prefix
BIORXIV_DOI_PREFIX = "10.1101/"


@dataclass
class PublicationStatus:
    """Result of checking a preprint's publication status."""

    preprint_id: str
    source: str  # "arxiv" or "doi" (for bioRxiv/medRxiv)
    title: str
    is_published: bool
    venue: str | None = None
    journal_name: str | None = None
    doi: str | None = None
    publication_date: str | None = None


@dataclass
class PreprintInfo:
    """Extracted preprint identifier."""

    preprint_id: str
    source: str  # "arxiv" or "doi"
    api_id: str  # ID formatted for Semantic Scholar API


def extract_preprint_info(
    url: str | None = None, doi: str | None = None, extra: str | None = None
) -> PreprintInfo | None:
    """Extract preprint ID from URL, DOI, or extra field.

    Supports:
      - arXiv: https://arxiv.org/abs/1706.03762, 10.48550/arXiv.1706.03762, arXiv:1706.03762
      - bioRxiv: https://www.biorxiv.org/content/10.1101/..., DOI 10.1101/...
      - medRxiv: https://www.medrxiv.org/content/10.1101/..., DOI 10.1101/...
    """
    # arXiv patterns
    arxiv_patterns = [
        r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)",
        r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d{7}(?:v\d+)?)",
        r"10\.48550/arXiv\.(\d{4}\.\d{4,5}(?:v\d+)?)",
        r"arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)",
    ]
    for source in [url or "", doi or "", extra or ""]:
        if not source:
            continue
        for pattern in arxiv_patterns:
            m = re.search(pattern, source, re.IGNORECASE)
            if m:
                aid = re.sub(r"v\d+$", "", m.group(1))
                return PreprintInfo(preprint_id=aid, source="arxiv", api_id=f"arXiv:{aid}")

    # bioRxiv/medRxiv: DOI starts with 10.1101/
    for source in [doi or "", url or ""]:
        if not source:
            continue
        m = re.search(r"(10\.1101/\d{4}\.\d{2}\.\d{2}\.\d+)(?:v\d+)?", source)
        if m:
            biorxiv_doi = m.group(1)
            return PreprintInfo(preprint_id=biorxiv_doi, source="doi", api_id=f"DOI:{biorxiv_doi}")

    return None


# Backward-compatible alias
def extract_arxiv_id(url: str | None = None, doi: str | None = None, extra: str | None = None) -> str | None:
    """Extract arXiv ID only (backward compatibility)."""
    info = extract_preprint_info(url=url, doi=doi, extra=extra)
    if info and info.source == "arxiv":
        return info.preprint_id
    return None


class SemanticScholarClient:
    """Client for Semantic Scholar API with rate limiting."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._delay = RATE_DELAY_WITH_KEY if api_key else RATE_DELAY_NO_KEY
        self._last_request_time: float = 0
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(timeout=REQUEST_TIMEOUT, headers=headers)

    def close(self) -> None:
        self._client.close()

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, api_url: str) -> dict | None:
        """Fetch from API with rate limiting and retry on 429."""
        self._rate_limit()
        try:
            resp = self._client.get(api_url)
        except httpx.HTTPError:
            return None

        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            time.sleep(self._delay * 2)
            self._last_request_time = time.time()
            try:
                resp = self._client.get(api_url)
            except httpx.HTTPError:
                return None
            if resp.status_code != 200:
                return None
        if resp.status_code != 200:
            return None
        return resp.json()  # type: ignore[no-any-return]

    def check_publication(self, info: PreprintInfo) -> PublicationStatus | None:
        """Check if a preprint has been formally published.

        Returns PublicationStatus or None if the paper is not found.
        """
        url = f"{API_BASE}/paper/{info.api_id}?fields={FIELDS}"
        data = self._fetch(url)
        if data is None:
            return None

        title = data.get("title", "")
        venue = data.get("venue") or None
        journal = data.get("journal") or {}
        journal_name = journal.get("name") if isinstance(journal, dict) else None
        pub_date = data.get("publicationDate")
        external_ids = data.get("externalIds", {})
        formal_doi = external_ids.get("DOI")

        # Publication venue info (more structured than venue string)
        pub_venue = data.get("publicationVenue") or {}
        if not journal_name and isinstance(pub_venue, dict):
            journal_name = pub_venue.get("name")

        # Determine if formally published:
        # - Must have a DOI that is NOT the preprint DOI itself
        # - Must have a venue/journal that is NOT a preprint server name
        is_preprint_doi = False
        if formal_doi:
            is_preprint_doi = formal_doi.startswith("10.48550/") or formal_doi.startswith(BIORXIV_DOI_PREFIX)

        preprint_venue_names = {"arxiv", "biorxiv", "medrxiv", "ssrn"}
        venue_is_preprint = False
        if venue and any(name in venue.lower() for name in preprint_venue_names):
            venue_is_preprint = True
        if journal_name and any(name in journal_name.lower() for name in preprint_venue_names):
            venue_is_preprint = True

        is_published = bool((venue or journal_name) and not venue_is_preprint and formal_doi and not is_preprint_doi)

        return PublicationStatus(
            preprint_id=info.preprint_id,
            source=info.source,
            title=title,
            is_published=is_published,
            venue=venue if venue else None,
            journal_name=journal_name,
            doi=formal_doi if formal_doi and not is_preprint_doi else None,
            publication_date=pub_date,
        )
