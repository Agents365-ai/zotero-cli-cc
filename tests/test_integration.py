"""End-to-end integration tests using the fixture DB."""
import json

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def _run(args, test_db_path, json_out=False):
    runner = CliRunner()
    base = ["--json"] if json_out else []
    return runner.invoke(main, base + args, env={"ZOT_DATA_DIR": str(test_db_path.parent)})


def test_full_read_workflow(test_db_path):
    """Search -> read -> notes -> export -> summarize -> relate."""
    # Search
    r = _run(["search", "transformer"], test_db_path, json_out=True)
    assert r.exit_code == 0
    items = json.loads(r.output)
    assert len(items) >= 1
    key = items[0]["key"]

    # Read
    r = _run(["read", key], test_db_path, json_out=True)
    assert r.exit_code == 0
    detail = json.loads(r.output)
    assert detail["title"]

    # Notes
    r = _run(["note", key], test_db_path)
    assert r.exit_code == 0

    # Export
    r = _run(["export", key], test_db_path)
    assert r.exit_code == 0
    assert "@" in r.output  # BibTeX

    # Summarize
    r = _run(["summarize", key], test_db_path)
    assert r.exit_code == 0
    assert "Title:" in r.output

    # Relate
    r = _run(["relate", key], test_db_path)
    assert r.exit_code == 0


def test_collection_workflow(test_db_path):
    """List collections -> list items in collection."""
    r = _run(["collection", "list"], test_db_path, json_out=True)
    assert r.exit_code == 0
    colls = json.loads(r.output)
    assert len(colls) >= 1

    r = _run(["collection", "items", "COLML01"], test_db_path, json_out=True)
    assert r.exit_code == 0
    items = json.loads(r.output)
    assert len(items) >= 2


def test_version():
    runner = CliRunner()
    r = runner.invoke(main, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.output
