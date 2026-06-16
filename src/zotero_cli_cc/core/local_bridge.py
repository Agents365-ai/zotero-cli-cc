"""Client for the `zot-cli-bridge` Zotero plugin on `127.0.0.1:23119`.

Zotero's built-in Web API does not expose "Find Full Text" — that feature
lives inside the desktop app because it relies on (a) the user's configured
PDF resolvers and (b) authenticated browser sessions / institutional
proxies. The `extension/zot-cli-bridge/` plugin shipped in this repo
exposes that capability over Zotero's local HTTP server so a CLI / agent
can trigger it.

This module is intentionally minimal: ping the bridge, and ask it to run
Find Full Text on a specific item key. Anything more elaborate belongs in
the plugin, not here.
"""

from __future__ import annotations

from typing import Any

import httpx

LOCAL_BASE = "http://127.0.0.1:23119"
PING_TIMEOUT = 5.0
# Find Full Text can be slow — it may try several resolvers in series, each
# of which can be a multi-second HTTP request through the user's proxy.
DEFAULT_TIMEOUT = 120.0


class LocalBridgeError(Exception):
    """Raised when the local Zotero HTTP bridge cannot satisfy a request.

    Attributes:
        code: machine-readable code (`not_reachable`, `bridge_missing`,
            `not_found`, `bridge_error`, `network_error`, `validation_error`).
        retryable: True for transient failures (timeout, 5xx, connection reset).
    """

    def __init__(self, message: str, *, code: str = "bridge_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _user_agent() -> str:
    # Important: Zotero's local server blocks requests whose UA starts with
    # "Mozilla/" (browser anti-CSRF). httpx's default UA is fine, but be
    # explicit so we don't break if httpx changes its default.
    return "zot-cli/local-bridge"


# The bridge is always on the loopback interface. httpx's default
# (trust_env=True) would route the request through any system/env HTTP proxy,
# which then returns 502 for a localhost target it can't reach. Disable env
# trust so loopback traffic always goes direct.
_TRUST_ENV = False


def ping(timeout: float = PING_TIMEOUT) -> dict[str, Any]:
    """Verify Zotero desktop + the bridge plugin are reachable.

    Raises LocalBridgeError with a specific code so callers can give the user
    actionable guidance (start Zotero / install the plugin / network).
    """
    try:
        resp = httpx.get(
            f"{LOCAL_BASE}/zot-cli/ping",
            timeout=timeout,
            headers={"User-Agent": _user_agent()},
            trust_env=_TRUST_ENV,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise LocalBridgeError(
            f"Cannot reach Zotero at {LOCAL_BASE} — is the desktop app running?",
            code="not_reachable",
            retryable=True,
        ) from e
    except httpx.HTTPError as e:
        raise LocalBridgeError(f"Bridge ping failed: {e}", code="network_error", retryable=True) from e

    if resp.status_code == 404:
        raise LocalBridgeError(
            "Zotero is running but the zot-cli-bridge plugin is not installed. See extension/zot-cli-bridge/README.md.",
            code="bridge_missing",
            retryable=False,
        )
    if resp.status_code != 200:
        raise LocalBridgeError(f"Bridge ping returned HTTP {resp.status_code}", code="bridge_error", retryable=True)
    return _parse_json(resp)


AUTODETECT_TIMEOUT = 2.0


def resolve_use_bridge(preference: bool | None) -> bool:
    """Decide whether an attach should route through the local desktop bridge.

    ``preference`` is the user's explicit choice: ``True`` forces the bridge,
    ``False`` forces the Web API, and ``None`` means auto-detect — prefer the
    bridge when the running desktop is reachable, otherwise fall back to the
    Web API. The probe is a fast loopback ping; any failure means "not up".
    """
    if preference is not None:
        return preference
    try:
        ping(timeout=AUTODETECT_TIMEOUT)
        return True
    except LocalBridgeError:
        return False


def find_pdf(
    item_key: str,
    *,
    library_id: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Trigger `Zotero.Attachments.addAvailableFile(item)` for `item_key`.

    Returns:
        dict with keys: `found` (bool), `attachment_key` (when found),
        `filename`, `content_type`, `message` (when not found).

    Raises:
        LocalBridgeError on any non-2xx response or network failure. A
        `not_found` code means the item key does not exist in the desktop
        library; `bridge_missing` means the plugin isn't installed.
    """
    payload: dict[str, Any] = {"key": item_key}
    if library_id is not None:
        payload["libraryID"] = library_id
    try:
        resp = httpx.post(
            f"{LOCAL_BASE}/zot-cli/find-pdf",
            json=payload,
            timeout=timeout,
            headers={"User-Agent": _user_agent()},
            trust_env=_TRUST_ENV,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise LocalBridgeError(
            f"Cannot reach Zotero at {LOCAL_BASE} — is the desktop app running?",
            code="not_reachable",
            retryable=True,
        ) from e
    except httpx.TimeoutException as e:
        raise LocalBridgeError(
            f"Find-PDF timed out after {timeout}s — resolvers may be slow",
            code="network_error",
            retryable=True,
        ) from e
    except httpx.HTTPError as e:
        raise LocalBridgeError(f"Bridge request failed: {e}", code="network_error", retryable=True) from e

    if resp.status_code == 404:
        # Could be "endpoint missing" (plugin not installed) or "item key not
        # found". The bridge's JSON disambiguates.
        body = _parse_json_or_none(resp)
        if body and body.get("error") == "item not found":
            raise LocalBridgeError(f"Item '{item_key}' not found in Zotero", code="not_found", retryable=False)
        raise LocalBridgeError(
            "The /zot-cli/find-pdf endpoint is missing — install the zot-cli-bridge plugin.",
            code="bridge_missing",
            retryable=False,
        )
    if resp.status_code == 400:
        body = _parse_json_or_none(resp) or {}
        raise LocalBridgeError(
            f"Bridge rejected request: {body.get('error', resp.text)}",
            code="validation_error",
            retryable=False,
        )
    if resp.status_code >= 500:
        raise LocalBridgeError(f"Bridge returned HTTP {resp.status_code}", code="bridge_error", retryable=True)
    if resp.status_code != 200:
        raise LocalBridgeError(
            f"Bridge returned HTTP {resp.status_code}: {resp.text}",
            code="bridge_error",
            retryable=False,
        )
    return _parse_json(resp)


RENAME_TIMEOUT = 30.0


def rename_attachment(
    attachment_key: str,
    new_name: str,
    *,
    library_id: int | None = None,
    force: bool = False,
    timeout: float = RENAME_TIMEOUT,
) -> dict[str, Any]:
    """Rename an attachment's stored file via the bridge's `renameAttachmentFile`.

    Returns a dict with `renamed`, `attachment_key`, `old_name`, `new_name`.

    Raises:
        LocalBridgeError. `bridge_missing` means the endpoint isn't registered
        (the installed plugin predates rename — re-run `zot bridge install`);
        `not_found` means the attachment/file is gone; `conflict` means the
        destination already exists (retry with `force`).
    """
    payload: dict[str, Any] = {"attachmentKey": attachment_key, "newName": new_name, "force": force}
    if library_id is not None:
        payload["libraryID"] = library_id
    try:
        resp = httpx.post(
            f"{LOCAL_BASE}/zot-cli/rename",
            json=payload,
            timeout=timeout,
            headers={"User-Agent": _user_agent()},
            trust_env=_TRUST_ENV,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise LocalBridgeError(
            f"Cannot reach Zotero at {LOCAL_BASE} — is the desktop app running?",
            code="not_reachable",
            retryable=True,
        ) from e
    except httpx.HTTPError as e:
        raise LocalBridgeError(f"Bridge request failed: {e}", code="network_error", retryable=True) from e

    if resp.status_code == 404:
        body = _parse_json_or_none(resp)
        if body and body.get("error"):
            raise LocalBridgeError(str(body["error"]), code="not_found", retryable=False)
        raise LocalBridgeError(
            "The /zot-cli/rename endpoint is missing — update the bridge plugin with 'zot bridge install'.",
            code="bridge_missing",
            retryable=False,
        )
    if resp.status_code == 409:
        body = _parse_json_or_none(resp) or {}
        raise LocalBridgeError(
            str(body.get("error", "destination file already exists")),
            code="conflict",
            retryable=False,
        )
    if resp.status_code == 400:
        body = _parse_json_or_none(resp) or {}
        raise LocalBridgeError(
            f"Bridge rejected request: {body.get('error', resp.text)}",
            code="validation_error",
            retryable=False,
        )
    if resp.status_code >= 500:
        raise LocalBridgeError(f"Bridge returned HTTP {resp.status_code}", code="bridge_error", retryable=True)
    if resp.status_code != 200:
        raise LocalBridgeError(
            f"Bridge returned HTTP {resp.status_code}: {resp.text}",
            code="bridge_error",
            retryable=False,
        )
    return _parse_json(resp)


IMPORT_TIMEOUT = 120.0


def import_file(
    parent_key: str,
    path: str,
    *,
    library_id: int | None = None,
    title: str | None = None,
    timeout: float = IMPORT_TIMEOUT,
) -> dict[str, Any]:
    """Import a local file as an attachment via the bridge's `importFromFile`.

    Unlike the Web-API upload path (`writer.upload_attachment`), this asks the
    running desktop to copy the file straight into its local storage, so the
    binary exists on disk immediately, cooperates with attachment-moving
    plugins (e.g. zotero-attanger), and syncs *up* to zotero.org afterwards.
    `path` must be an absolute path the desktop process can read (the CLI and
    Zotero share the machine).

    Returns a dict with `imported`, `attachment_key`, `parent_key`, `filename`,
    `content_type`.

    Raises:
        LocalBridgeError. `bridge_missing` means the endpoint isn't registered
        (the installed plugin predates import — re-run `zot bridge install`,
        needs v0.3.0+); `not_found` means the parent item or the file is gone.
    """
    payload: dict[str, Any] = {"parentKey": parent_key, "path": path}
    if library_id is not None:
        payload["libraryID"] = library_id
    if title is not None:
        payload["title"] = title
    try:
        resp = httpx.post(
            f"{LOCAL_BASE}/zot-cli/import-file",
            json=payload,
            timeout=timeout,
            headers={"User-Agent": _user_agent()},
            trust_env=_TRUST_ENV,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise LocalBridgeError(
            f"Cannot reach Zotero at {LOCAL_BASE} — is the desktop app running?",
            code="not_reachable",
            retryable=True,
        ) from e
    except httpx.HTTPError as e:
        raise LocalBridgeError(f"Bridge request failed: {e}", code="network_error", retryable=True) from e

    if resp.status_code == 404:
        # Disambiguate "endpoint missing" (old plugin) from "parent/file gone".
        body = _parse_json_or_none(resp)
        if body and body.get("error"):
            raise LocalBridgeError(str(body["error"]), code="not_found", retryable=False)
        raise LocalBridgeError(
            "The /zot-cli/import-file endpoint is missing — update the bridge plugin with 'zot bridge install'.",
            code="bridge_missing",
            retryable=False,
        )
    if resp.status_code == 400:
        body = _parse_json_or_none(resp) or {}
        raise LocalBridgeError(
            f"Bridge rejected request: {body.get('error', resp.text)}",
            code="validation_error",
            retryable=False,
        )
    if resp.status_code >= 500:
        raise LocalBridgeError(f"Bridge returned HTTP {resp.status_code}", code="bridge_error", retryable=True)
    if resp.status_code != 200:
        raise LocalBridgeError(
            f"Bridge returned HTTP {resp.status_code}: {resp.text}",
            code="bridge_error",
            retryable=False,
        )
    return _parse_json(resp)


def _parse_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as e:
        raise LocalBridgeError(f"Bridge returned invalid JSON: {e}", code="bridge_error") from e
    if not isinstance(data, dict):
        raise LocalBridgeError("Bridge returned non-object JSON", code="bridge_error")
    return data


def _parse_json_or_none(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None
