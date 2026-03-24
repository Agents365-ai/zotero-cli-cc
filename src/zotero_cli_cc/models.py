from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Creator:
    first_name: str
    last_name: str
    creator_type: str

    @property
    def full_name(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts)


@dataclass
class Item:
    key: str
    item_type: str
    title: str
    creators: list[Creator]
    abstract: str | None
    date: str | None
    url: str | None
    doi: str | None
    tags: list[str]
    collections: list[str]
    date_added: str
    date_modified: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Note:
    key: str
    parent_key: str
    content: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Collection:
    key: str
    name: str
    parent_key: str | None
    children: list[Collection] = field(default_factory=list)


@dataclass
class Attachment:
    key: str
    parent_key: str
    filename: str
    content_type: str
    path: Path | None = None


@dataclass
class ErrorInfo:
    message: str
    context: str = ""
    hint: str = ""


@dataclass
class SearchResult:
    items: list[Item]
    total: int
    query: str


@dataclass
class DuplicateGroup:
    items: list[Item]
    match_type: str  # "doi" | "title"
    score: float  # 1.0 for DOI exact match, 0.0-1.0 for title similarity
