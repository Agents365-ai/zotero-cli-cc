# Command Reference

## Search & Browse

```bash
zot --json search "transformer attention"
zot --json search "BERT" --collection "NLP"
zot --json list --collection "Machine Learning" --limit 10
zot --json read ITEMKEY
zot --json relate ITEMKEY
```

## Notes & Tags

```bash
zot --json note ITEMKEY
zot note ITEMKEY --add "Key finding: ..."
zot --json tag ITEMKEY
zot tag ITEMKEY --add "important"
zot tag ITEMKEY --remove "to-read"
```

## Citation Export

```bash
zot export ITEMKEY                    # BibTeX (default)
zot export ITEMKEY --format csl-json  # CSL-JSON
zot export ITEMKEY --format ris       # RIS
zot export ITEMKEY --format json      # Raw JSON

# Formatted citation (copies to clipboard)
zot cite ITEMKEY                      # APA (default)
zot cite ITEMKEY --style nature       # Nature
zot cite ITEMKEY --style vancouver    # Vancouver
```

## Item Management (Write Ops)

```bash
zot add --doi "10.1038/s41586-023-06139-9"
zot add --url "https://arxiv.org/abs/2301.00001"
zot add --from-file dois.txt              # Batch import (one DOI/URL per line)
zot add --pdf paper.pdf                   # Add from local PDF (auto-extract DOI)
zot --no-interaction delete ITEMKEY
zot update ITEMKEY --title "New Title"
zot update ITEMKEY --field volume=42 --field pages=1-10
zot attach ITEMKEY --file supplement.pdf
```

### Safety Flags

```bash
# Preview without writing — no API call
zot add --doi "10.1038/..." --dry-run
zot delete ITEMKEY --dry-run
zot update ITEMKEY --field volume=42 --dry-run

# Idempotency — safe retry after network failure
zot add --doi "10.1038/..." --idempotency-key abc-123
zot update ITEMKEY --title "X" --idempotency-key abc-124
zot attach ITEMKEY --file x.pdf --idempotency-key abc-125
zot delete ITEMKEY --yes --idempotency-key abc-126
```

## Find Full Text PDF (Zotero desktop bridge)

`zot find-pdf` triggers Zotero desktop's "Find Full Text", reusing the
desktop's configured PDF resolvers AND its authenticated sessions /
institutional proxies. This is the only way to reach paywalled PDFs from the
CLI — the Zotero Web API cannot do it. Requires Zotero running with the
`zot-cli-bridge` plugin installed.

```bash
zot find-pdf ITEMKEY                  # find & attach a PDF via desktop resolvers
zot find-pdf ITEMKEY --dry-run        # only check the bridge is reachable
zot find-pdf ITEMKEY --timeout 180    # give slow resolvers more time
zot find-pdf ITEMKEY --library-id 42  # target a specific library
```

One-time bridge setup (enables `find-pdf`):

```bash
zot bridge install                    # build the plugin .xpi + print install steps
zot bridge install --output ~/zot-cli-bridge.xpi   # choose where to write the .xpi
zot bridge status                     # check Zotero + plugin reachability
zot bridge uninstall                  # show how to remove the plugin
```

`zot bridge install` builds the `.xpi`; you finish installation in Zotero via
Tools -> Plugins -> gear -> Install Plugin From File (Zotero owns plugin
installation, so the CLI cannot sideload silently).

## Collections

```bash
zot --json collection list
zot --json collection items COLLECTIONKEY
zot collection create "New Project"
zot collection move ITEMKEY COLLECTIONKEY
zot collection rename COLLECTIONKEY "New Name"
zot collection delete COLLECTIONKEY
```

## Duplicates, Recent & Trash

```bash
zot --json duplicates                # DOI + title matching
zot --json duplicates --by title     # Title-only matching
zot --json recent --days 7           # Recently added
zot --json recent --sort dateModified
zot --json trash list                # View trashed items
zot trash restore ITEMKEY            # Restore from trash
```

## PDF & Summarization

```bash
zot --json pdf ITEMKEY                      # Full text extraction
zot --json pdf --outline ITEMKEY            # Section headings + secid
zot --json pdf --section SECID ITEMKEY      # Extract specific section
zot pdf ITEMKEY --annotations               # PDF annotations
zot --json summarize ITEMKEY
zot summarize-all
```

**Token-saving strategy**: For large PDFs, use `--outline` to get section IDs first, then `--section` to extract only what you need.

## Utilities

```bash
zot --json stats                     # Library statistics
zot open ITEMKEY                     # Open PDF in system viewer
zot open --url ITEMKEY               # Open URL/DOI in browser
zot update-status --limit 20        # Check preprint publication status (needs S2_API_KEY)
```

## Group Library

```bash
zot --library group:12345 search "query"
zot --library group:12345 list
```

All commands support `--library group:<id>` to operate on group libraries.
