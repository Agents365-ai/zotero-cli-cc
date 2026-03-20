from __future__ import annotations

from pyzotero import zotero
from pyzotero.zotero_errors import ResourceNotFoundError
from httpx import ConnectError as HttpxConnectError


SYNC_REMINDER = "Change saved. Run Zotero sync to update local database."


class ZoteroWriteError(Exception):
    """Raised when a Zotero write operation fails."""
    pass


class ZoteroWriter:
    def __init__(self, library_id: str, api_key: str) -> None:
        self._zot = zotero.Zotero(library_id, "user", api_key)

    def _check_response(self, resp: dict) -> str:
        """Check create response, return key or raise error."""
        if resp.get("successful") and "0" in resp["successful"]:
            return resp["successful"]["0"]["key"]
        failed = resp.get("failed", {})
        if failed:
            msg = failed.get("0", {}).get("message", "Unknown API error")
            raise ZoteroWriteError(f"API error: {msg}")
        raise ZoteroWriteError("Unexpected API response")

    def add_note(self, parent_key: str, content: str) -> str:
        try:
            template = self._zot.item_template("note")
            template["note"] = content
            template["parentItem"] = parent_key
            resp = self._zot.create_items([template])
            return self._check_response(resp)
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def update_note(self, note_key: str, content: str) -> None:
        try:
            item = self._zot.item(note_key)
            item["data"]["note"] = content
            self._zot.update_item(item)
        except ResourceNotFoundError:
            raise ZoteroWriteError(f"Note '{note_key}' not found")
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def add_item(self, doi: str | None = None, url: str | None = None) -> str:
        if not doi and not url:
            raise ValueError("Either doi or url must be provided")
        try:
            if doi:
                template = self._zot.item_template("journalArticle")
                template["DOI"] = doi
                resp = self._zot.create_items([template])
                return self._check_response(resp)
            template = self._zot.item_template("webpage")
            template["url"] = url
            resp = self._zot.create_items([template])
            return self._check_response(resp)
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def delete_item(self, key: str) -> None:
        try:
            item = self._zot.item(key)
            self._zot.delete_item(item)
        except ResourceNotFoundError:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def add_tags(self, key: str, tags: list[str]) -> None:
        try:
            item = self._zot.item(key)
            existing = [t["tag"] for t in item["data"].get("tags", [])]
            new_tags = [{"tag": t} for t in set(existing + tags)]
            item["data"]["tags"] = new_tags
            self._zot.update_item(item)
        except ResourceNotFoundError:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def remove_tags(self, key: str, tags: list[str]) -> None:
        try:
            item = self._zot.item(key)
            item["data"]["tags"] = [
                t for t in item["data"].get("tags", []) if t["tag"] not in tags
            ]
            self._zot.update_item(item)
        except ResourceNotFoundError:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def create_collection(self, name: str, parent_key: str | None = None) -> str:
        try:
            payload = [{"name": name, "parentCollection": parent_key or False}]
            resp = self._zot.create_collections(payload)
            return self._check_response(resp)
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def move_to_collection(self, item_key: str, collection_key: str) -> None:
        try:
            self._zot.addto_collection(collection_key, self._zot.item(item_key))
        except ResourceNotFoundError:
            raise ZoteroWriteError(f"Item or collection not found")
        except HttpxConnectError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e
