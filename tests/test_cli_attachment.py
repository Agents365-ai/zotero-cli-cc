from __future__ import annotations

import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def _copy_fixture_db(tmp_path: Path, fixture_db: Path) -> Path:
    db_path = tmp_path / "zotero.sqlite"
    shutil.copy2(fixture_db, db_path)
    return db_path


def _create_pdf(data_dir: Path, attachment_key: str = "ATCH005", filename: str = "attention.pdf") -> Path:
    pdf_path = data_dir / "storage" / attachment_key / filename
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 test\n")
    return pdf_path


def _invoke(args: list[str], data_dir: Path):
    runner = CliRunner()
    return runner.invoke(main, args, env={"ZOT_DATA_DIR": str(data_dir), "ZOT_FORMAT": "table"})


def test_attachment_path_human_outputs_bare_existing_path(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)
    pdf_path = _create_pdf(tmp_path)

    result = _invoke(["attachment", "path", "ATTN001"], tmp_path)

    assert result.exit_code == 0
    assert result.output.strip() == str(pdf_path)


def test_attachment_path_json_envelope(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)
    pdf_path = _create_pdf(tmp_path)

    result = _invoke(["--json", "attachment", "path", "ATTN001"], tmp_path)

    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["item_key"] == "ATTN001"
    assert env["data"]["attachment_key"] == "ATCH005"
    assert env["data"]["path"] == str(pdf_path)
    assert env["data"]["filename"] == "attention.pdf"
    assert env["data"]["exists"] is True
    assert env["data"]["mime_type"] == "application/pdf"


def test_attachment_path_direct_attachment_key_is_not_supported(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)

    result = _invoke(["--json", "attachment", "path", "ATCH005"], tmp_path)

    assert result.exit_code == 4
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"
    assert "Item 'ATCH005' not found" in env["error"]["message"]


def test_attachment_path_no_pdf_is_not_found(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)

    result = _invoke(["--json", "attachment", "path", "DEEP003"], tmp_path)

    assert result.exit_code == 4
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"
    assert "No PDF attachment" in env["error"]["message"]


def test_attachment_path_missing_local_file_is_not_found(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)

    result = _invoke(["--json", "attachment", "path", "ATTN001"], tmp_path)

    assert result.exit_code == 4
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"
    assert "PDF file not found" in env["error"]["message"]


def test_attachment_path_missing_item_is_not_found(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)

    result = _invoke(["--json", "attachment", "path", "NOITEM"], tmp_path)

    assert result.exit_code == 4
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"
    assert "Item 'NOITEM' not found" in env["error"]["message"]


def test_attachment_path_uses_first_pdf_for_multi_pdf_item(tmp_path: Path, test_db_path: Path):
    _copy_fixture_db(tmp_path, test_db_path)
    translated_path = _create_pdf(tmp_path, "ATCH012", "translated_cn.pdf")
    _create_pdf(tmp_path, "ATCH013", "original.pdf")

    result = _invoke(["--json", "attachment", "path", "BILI011"], tmp_path)

    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["attachment_key"] == "ATCH012"
    assert env["data"]["filename"] == "translated_cn.pdf"
    assert env["data"]["path"] == str(translated_path)


def test_schema_attachment_path_reflects_command():
    result = CliRunner().invoke(main, ["schema", "attachment", "path"])

    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["name"] == "attachment path"
    assert env["data"]["safety_tier"] == "read"
    assert env["data"]["params"] == [
        {"name": "item_key", "kind": "argument", "type": "string", "required": True}
    ]
