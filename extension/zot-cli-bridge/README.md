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
plugin enables. It registers two endpoints on `http://127.0.0.1:23119`:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/zot-cli/ping` | Health probe — returns plugin + Zotero version |
| `POST` | `/zot-cli/find-pdf` | Body: `{"key": "ABCD1234"}`. Triggers `Zotero.Attachments.addAvailableFile(item)` and returns the attached PDF's key on success, or `{found: false}` if no resolver had a hit. |

## Install

1. Download the latest `zot-cli-bridge.xpi` from the
   [Releases page](https://github.com/Agents365-ai/zotero-cli-cc/releases)
   (or build it locally — see below).
2. In Zotero: **Tools → Plugins → ⚙ → Install plugin from file…**, pick the
   `.xpi`, restart Zotero.
3. Verify it's wired up:
   ```bash
   curl http://127.0.0.1:23119/zot-cli/ping
   # {"ok": true, "bridge_version": "0.1.0", "zotero_version": "7.x.y", ...}
   ```

You can now run `zot find-pdf <item-key>` from the parent repo.

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
