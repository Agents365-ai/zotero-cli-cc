# Contributing to zotero-cli-cc

Thanks for your interest in contributing!

## License of contributions

zotero-cli-cc is **dual-licensed** under the GNU AGPL-3.0-or-later and a
separate commercial license (see [LICENSE](LICENSE) and
[LICENSE-COMMERCIAL](LICENSE-COMMERCIAL)).

By submitting a contribution (a pull request, patch, or commit), you agree that:

1. You are the author of the contribution, or are otherwise entitled to submit
   it under these terms.
2. Your contribution is licensed under the AGPL-3.0-or-later, **and** you grant
   the project owner the right to also offer your contribution under the
   project's commercial license and to relicense it as part of the project's
   dual-licensing model.

This lets the project stay open source while remaining usable in commercial
products. If you cannot agree to this, please do not submit a contribution.

## Developer Certificate of Origin (DCO)

Sign off each commit (`git commit -s`) to certify the
[Developer Certificate of Origin](https://developercertificate.org/):

    Signed-off-by: Your Name <your.email@example.com>

## Development

See [CLAUDE.md](CLAUDE.md) and the docs for setup, linting, and tests. In short:

```bash
uv sync --group dev --extra mcp
uv run ruff check src/ tests/
uv run mypy src/zotero_cli_cc/
uv run pytest tests/ -v
```
