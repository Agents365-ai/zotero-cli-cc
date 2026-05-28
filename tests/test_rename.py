"""Tests for `zot rename` — naming/classification logic and the CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.local_bridge import LocalBridgeError
from zotero_cli_cc.core.rename import (
    RenameError,
    build_plan,
    classify_pdfs,
    extract_year,
    is_pdf,
    is_supplementary,
    journal_short,
    resolve_template,
)
from zotero_cli_cc.models import Attachment, Creator, Item


def _item(*, item_type="journalArticle", title="A Title", date="2016-05-01", tags=None, creators=None, **extra) -> Item:
    return Item(
        key="ITEM0001",
        item_type=item_type,
        title=title,
        creators=creators or [],
        abstract=None,
        date=date,
        url=None,
        doi=None,
        tags=tags or [],
        collections=[],
        date_added="2020-01-01",
        date_modified="2020-01-01",
        extra=extra,
    )


def _att(key: str, filename: str, content_type: str = "application/pdf") -> Attachment:
    return Attachment(key=key, parent_key="ITEM0001", filename=filename, content_type=content_type)


# ---------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------


class TestJournalShort:
    def test_jab_tag_wins(self):
        item = _item(tags=["Jab/#TOG"], publicationTitle="ACM Transactions on Graphics")
        assert journal_short(item) == "TOG"

    def test_journal_article_abbrev(self):
        item = _item(publicationTitle="IEEE Transactions on Pattern Analysis and Machine Intelligence")
        assert journal_short(item) == "TPAMI"

    def test_arxiv_is_preprint(self):
        item = _item(publicationTitle="arXiv:1706.03762")
        assert journal_short(item) == "Pre"

    def test_conference_paren_abbrev(self):
        item = _item(item_type="conferencePaper", conferenceName="Conference on Computer Vision (CVPR)")
        assert journal_short(item) == "CVPR"

    def test_book_section_eccv(self):
        item = _item(item_type="bookSection", bookTitle="Computer Vision - ECCV 2020")
        assert journal_short(item) == "ECCV"

    def test_preprint_type(self):
        assert journal_short(_item(item_type="preprint")) == "Pre"

    def test_unknown_falls_back(self):
        assert journal_short(_item(item_type="thesis")) == "Pre"

    def test_single_word_journal_kept_whole(self):
        # "Nature" must not collapse to a useless single letter "N".
        assert journal_short(_item(publicationTitle="Nature")) == "Nature"


class TestYearAndTemplate:
    def test_extract_year(self):
        assert extract_year(_item(date="2016-05-01")) == "2016"
        assert extract_year(_item(date=None)) == ""

    def test_default_template(self):
        item = _item(publicationTitle="IEEE Transactions on Pattern Analysis and Machine Intelligence", title="Go-ICP")
        assert resolve_template("{journal}_{year}_{title}", item) == "TPAMI_2016_Go-ICP"

    def test_unknown_token_rejected(self):
        with pytest.raises(RenameError):
            resolve_template("{journal}_{foo}", _item())

    def test_empty_name_rejected(self):
        with pytest.raises(RenameError):
            resolve_template("{title}", _item(title=""))

    def test_author_and_shorttitle_tokens(self):
        item = _item(creators=[Creator("Kaiming", "He", "author")], shortTitle="ResNet")
        assert resolve_template("{author}_{shorttitle}", item) == "He_ResNet"

    def test_empty_year_collapses_separators(self):
        # No date -> the {year} slot is empty; must not leave "TPAMI__X".
        item = _item(
            publicationTitle="IEEE Transactions on Pattern Analysis and Machine Intelligence",
            title="X",
            date=None,
        )
        assert resolve_template("{journal}_{year}_{title}", item) == "TPAMI_X"

    def test_title_prefers_short_title(self):
        item = _item(title="A Very Long Full Title Here", shortTitle="Short")
        assert resolve_template("{title}", item) == "Short"

    def test_fulltitle_token_uses_full(self):
        item = _item(title="A Very Long Full Title Here", shortTitle="Short")
        assert resolve_template("{fulltitle}", item) == "A Very Long Full Title Here"

    def test_long_title_truncated_to_byte_cap(self):
        item = _item(publicationTitle="Nature", title="word " * 100)
        base = resolve_template("{title}", item)
        assert len(base.encode("utf-8")) <= 180


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


class TestClassify:
    def test_is_pdf_and_filters_excel(self):
        assert is_pdf(_att("A", "x.pdf"))
        assert not is_pdf(_att("B", "data.xlsx", "application/vnd.ms-excel"))

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("paper_supp.pdf", True),
            ("supplementary.pdf", True),
            ("main_SI.pdf", True),
            ("appendix.pdf", True),
            ("vision.pdf", False),
            ("paper.pdf", False),
        ],
    )
    def test_is_supplementary(self, name, expected):
        assert is_supplementary(name) is expected

    def test_main_and_supp_split(self):
        atts = [_att("A", "paper.pdf"), _att("B", "paper_supp.pdf"), _att("C", "data.xlsx", "application/vnd.ms-excel")]
        main, supps = classify_pdfs(atts)
        assert main is not None and main.key == "A"
        assert [s.key for s in supps] == ["B"]

    def test_all_supp_promotes_first(self):
        atts = [_att("A", "a_supp.pdf"), _att("B", "b_supp.pdf")]
        main, supps = classify_pdfs(atts)
        assert main.key == "A"
        assert [s.key for s in supps] == ["B"]

    def test_multiple_non_supp_first_is_main(self):
        atts = [_att("A", "a.pdf"), _att("B", "b.pdf")]
        main, supps = classify_pdfs(atts)
        assert main.key == "A"
        assert [s.key for s in supps] == ["B"]

    def test_no_pdfs(self):
        main, supps = classify_pdfs([_att("A", "data.xlsx", "application/vnd.ms-excel")])
        assert main is None and supps == []


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def _item_tpami(self):
        return _item(publicationTitle="IEEE Transactions on Pattern Analysis and Machine Intelligence", title="Go-ICP")

    def test_main_plus_supp_suffix(self):
        atts = [_att("A", "paper.pdf"), _att("B", "supp.pdf"), _att("C", "supp2.pdf")]
        plan = build_plan(self._item_tpami(), atts)
        assert [(e.role, e.new_name) for e in plan] == [
            ("main", "TPAMI_2016_Go-ICP.pdf"),
            ("supp", "TPAMI_2016_Go-ICP_SI.pdf"),
            ("supp", "TPAMI_2016_Go-ICP_SI2.pdf"),
        ]

    def test_main_only(self):
        atts = [_att("A", "paper.pdf"), _att("B", "supp.pdf")]
        plan = build_plan(self._item_tpami(), atts, include_supp=False)
        assert len(plan) == 1 and plan[0].role == "main"

    def test_skip_when_unchanged(self):
        atts = [_att("A", "TPAMI_2016_Go-ICP.pdf")]
        plan = build_plan(self._item_tpami(), atts)
        assert plan[0].skip is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _invoke(args, test_db_path: Path, json_out=False):
    runner = CliRunner()
    base = ["--json"] if json_out else []
    env = {"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base + args, env=env)


class TestRenameCLI:
    def test_dry_run_reads_db(self, test_db_path):
        result = _invoke(["rename", "ATTN001", "--dry-run"], test_db_path, json_out=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["renamed_count"] == 0
        renames = data["results"][0]["renames"]
        assert renames[0]["status"] == "dry-run"
        assert renames[0]["new_name"].endswith(".pdf")

    def test_dry_run_main_and_supp(self, test_db_path):
        result = _invoke(["rename", "BILI011", "--dry-run"], test_db_path, json_out=True)
        data = json.loads(result.output)["data"]
        roles = [r["role"] for r in data["results"][0]["renames"]]
        assert "main" in roles and "supp" in roles

    def test_main_only_flag(self, test_db_path):
        result = _invoke(["rename", "BILI011", "--dry-run", "--main-only"], test_db_path, json_out=True)
        data = json.loads(result.output)["data"]
        roles = [r["role"] for r in data["results"][0]["renames"]]
        assert roles == ["main"]

    def test_attachment_without_name_errors(self, test_db_path):
        result = _invoke(["rename", "--attachment", "ATT1"], test_db_path)
        assert result.exit_code == 3

    def test_no_keys_errors(self, test_db_path):
        result = _invoke(["rename"], test_db_path)
        assert result.exit_code == 3

    def test_explicit_rename(self, test_db_path, monkeypatch):
        called = {}

        def fake_rename(att, name, **kw):
            called["att"] = att
            called["name"] = name
            return {"renamed": True, "old_name": "old.pdf", "new_name": name}

        monkeypatch.setattr("zotero_cli_cc.commands.rename.rename_attachment", fake_rename)
        result = _invoke(["rename", "--attachment", "ATT1", "--name", "X.pdf"], test_db_path, json_out=True)
        assert result.exit_code == 0
        assert called == {"att": "ATT1", "name": "X.pdf"}
        data = json.loads(result.output)["data"]
        assert data["renamed_count"] == 1

    def test_not_reachable_aborts(self, test_db_path, monkeypatch):
        def boom(*a, **k):
            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr("zotero_cli_cc.commands.rename.ping", boom)
        result = _invoke(["rename", "ATTN001"], test_db_path)
        assert result.exit_code == 5

    def test_bridge_missing_aborts(self, test_db_path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.rename.ping", lambda *a, **k: {"bridge_version": "0.1.0"})

        def boom(*a, **k):
            raise LocalBridgeError("no endpoint", code="bridge_missing", retryable=False)

        monkeypatch.setattr("zotero_cli_cc.commands.rename.rename_attachment", boom)
        result = _invoke(["rename", "ATTN001"], test_db_path)
        assert result.exit_code == 3

    def test_conflict_recorded_inline(self, test_db_path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.rename.ping", lambda *a, **k: {"bridge_version": "0.2.0"})

        def conflict(*a, **k):
            raise LocalBridgeError("exists", code="conflict", retryable=False)

        monkeypatch.setattr("zotero_cli_cc.commands.rename.rename_attachment", conflict)
        result = _invoke(["rename", "ATTN001"], test_db_path, json_out=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        statuses = [r["status"] for r in data["results"][0]["renames"]]
        assert "error" in statuses
