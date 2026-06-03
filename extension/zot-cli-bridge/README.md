# Zot CLI Bridge — Zotero plugin

A tiny Zotero 7 plugin that exposes Zotero's built-in **"Find Full Text"** over
the desktop's local HTTP server, so the [`zot`](../..) CLI (and AI agents
driving it) can trigger PDF retrieval without leaving the terminal.

## Why a plugin

Zotero's Find Full Text uses two things that Web-API clients cannot reach:

1. The user's configured **PDF resolvers** (DOI, OpenURL, Google Scholar
   fallback, custom resolvers, LibKey, …).
2. The desktop app's **authenticated sessions / institutional proxies** — i.e.
   the cookies you've already established by logging into your library.

Both live inside the running Zotero process. The only safe way to drive them
from outside is to ask Zotero itself to do the work, which is what this
plugin enables. It registers these endpoints on `http://127.0.0.1:23119`:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/zot-cli/ping` | Health probe — returns plugin + Zotero version |
| `POST` | `/zot-cli/find-pdf` | Body: `{"key": "ABCD1234"}`. Triggers `Zotero.Attachments.addAvailableFile(item)` and returns the attached PDF's key on success, or `{found: false}` if no resolver had a hit. |
| `POST` | `/zot-cli/rename` | Body: `{"attachmentKey": "...", "newName": "X.pdf", "force": false}`. Calls `item.renameAttachmentFile(newName, force)` on the attachment, syncs its title, and returns `{renamed, old_name, new_name}`. Powers `zot rename`. |
| `POST` | `/zot-cli/import-file` | Body: `{"parentKey": "...", "path": "/abs/file.pdf", "title": "..."}`. Calls `Zotero.Attachments.importFromFile(...)` so the file is copied into **local** storage immediately (vs a Web-API upload that lands cloud-only). Returns `{imported, attachment_key, filename, content_type}`. Powers `zot attach --via-bridge`. |

## Install

### Recommended: `zot bridge install`

If you have the `zot` CLI installed, let it build the `.xpi` for you, then
install it through Zotero's plugin manager (modern Zotero won't accept a
CLI-sideloaded plugin, so this is the reliable path):

```bash
zot bridge install
# -> Built bridge plugin: ~/.cache/zot/zot-cli-bridge.xpi
#    In Zotero: Tools -> Plugins -> gear -> Install Plugin From File...
#    pick that .xpi, then restart Zotero.
zot bridge status        # verify -> Bridge OK
```

### Manual

1. Download the latest `zot-cli-bridge.xpi` from the
   [Releases page](https://github.com/Agents365-ai/zotero-cli-cc/releases)
   (or build it locally — see below).
2. In Zotero: **Tools → Plugins → ⚙ → Install plugin from file…**, pick the
   `.xpi`, restart Zotero.
3. Verify it's wired up:
   ```bash
   curl http://127.0.0.1:23119/zot-cli/ping
   # {"ok": true, "bridge_version": "0.3.0", "zotero_version": "9.x.y", ...}
   ```

You can now run `zot find-pdf <item-key>` and `zot attach <key> --file <path> --via-bridge` from the parent repo.

> **Manifest note:** the plugin manifest must include `icons` and
> `applications.zotero.update_url`. Zotero 8/9 reject a manifest without them
> as "incompatible with this version of Zotero".

## Build locally

The plugin is plain JS + a manifest; there's no build step:

```bash
cd extension/zot-cli-bridge
zip -r ../zot-cli-bridge.xpi manifest.json bootstrap.js
```

Then install via **Tools → Plugins → Install plugin from file…**.

## Security notes

- The Zotero local HTTP server only listens on `127.0.0.1` — never on the
  network — so a browser tab on the same machine is the only realistic
  cross-origin attacker. Zotero already blocks browser-origin requests
  (`Origin:` header or Mozilla UA) on non-allowlisted endpoints; this
  plugin **does not** set `allowRequestsFromUnsafeWebContent`, so those
  protections apply to `/zot-cli/find-pdf` too.
- The endpoint only triggers an action Zotero already exposes via right-click
  → Find Full Text. It does not bypass auth, doesn't accept arbitrary code,
  and doesn't read or modify other items beyond the one whose `key` you pass.

## License

CC-BY-NC-4.0 (matches the parent repo).
