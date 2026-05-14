"""Tests for the Crossref DOI metadata resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from zotero_cli_cc.core.metadata_resolver import (
    MetadataResolveError,
    _strip_jats,
    map_crossref_to_zotero,
    resolve_doi,
)


def _mock_response(status: int, payload: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = payload or {}
    return resp


class TestMapCrossrefToZotero:
    def test_full_article(self) -> None:
        message = {
            "DOI": "10.1038/s41586-023-06139-9",
            "title": ["Highly accurate protein structure prediction"],
            "container-title": ["Nature"],
            "short-container-title": ["Nature"],
            "publisher": "Springer Nature",
            "volume": "596",
            "issue": "7873",
            "page": "583-589",
            "ISSN": ["0028-0836", "1476-4687"],
            "language": "en",
            "URL": "https://doi.org/10.1038/s41586-023-06139-9",
            "abstract": "<jats:p>Some <jats:italic>abstract</jats:italic>  text.</jats:p>",
            "published-print": {"date-parts": [[2023, 7, 13]]},
            "author": [
                {"given": "John", "family": "Jumper", "sequence": "first"},
                {"given": "Richard", "family": "Evans", "sequence": "additional"},
            ],
        }
        fields = map_crossref_to_zotero(message)
        assert fields["title"] == "Highly accurate protein structure prediction"
        assert fields["publicationTitle"] == "Nature"
        assert "journalAbbreviation" not in fields  # same as container — suppress duplicate
        assert fields["volume"] == "596"
        assert fields["issue"] == "7873"
        assert fields["pages"] == "583-589"
        assert fields["ISSN"] == "0028-0836"
        assert fields["date"] == "2023-07-13"
        assert fields["DOI"] == "10.1038/s41586-023-06139-9"
        assert fields["abstractNote"] == "Some abstract text."
        assert fields["creators"] == [
            {"creatorType": "author", "firstName": "John", "lastName": "Jumper"},
            {"creatorType": "author", "firstName": "Richard", "lastName": "Evans"},
        ]

    def test_distinct_short_container(self) -> None:
        message = {
            "title": ["x"],
            "container-title": ["Proceedings of the National Academy of Sciences"],
            "short-container-title": ["PNAS"],
        }
        fields = map_crossref_to_zotero(message)
        assert fields["publicationTitle"] == "Proceedings of the National Academy of Sciences"
        assert fields["journalAbbreviation"] == "PNAS"

    def test_falls_back_to_online_then_issued(self) -> None:
        message = {"title": ["x"], "published-online": {"date-parts": [[2024, 3]]}}
        assert map_crossref_to_zotero(message)["date"] == "2024-03"
        message = {"title": ["x"], "issued": {"date-parts": [[2020]]}}
        assert map_crossref_to_zotero(message)["date"] == "2020"

    def test_corporate_author(self) -> None:
        message = {"title": ["x"], "author": [{"name": "The Consortium"}]}
        creators = map_crossref_to_zotero(message)["creators"]
        assert creators == [{"creatorType": "author", "name": "The Consortium"}]

    def test_omits_missing_fields(self) -> None:
        # Only title — nothing else should leak into the output.
        message = {"title": ["only this"]}
        fields = map_crossref_to_zotero(message)
        assert fields == {"title": "only this"}

    def test_strip_jats_handles_nested_tags(self) -> None:
        assert _strip_jats("<jats:p>a <jats:i>b</jats:i> c</jats:p>") == "a b c"
        assert _strip_jats("plain text") == "plain text"


class TestResolveDoi:
    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_success(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            200,
            {
                "message": {
                    "DOI": "10.1/x",
                    "title": ["A paper"],
                    "container-title": ["Journal X"],
                    "issued": {"date-parts": [[2024]]},
                    "author": [{"given": "A", "family": "B"}],
                }
            },
        )
        fields = resolve_doi("10.1/x")
        assert fields is not None
        assert fields["title"] == "A paper"
        assert fields["publicationTitle"] == "Journal X"
        assert fields["date"] == "2024"
        # Verify the URL and user-agent header are sane.
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://api.crossref.org/works/10.1/x"
        headers = mock_get.call_args.kwargs["headers"]
        assert "zotero-cli-cc" in headers["User-Agent"]

    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_404_returns_none(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(404)
        assert resolve_doi("10.1/missing") is None

    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_5xx_raises(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(503)
        with pytest.raises(MetadataResolveError, match="503"):
            resolve_doi("10.1/x")

    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_network_error_raises(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = httpx.ConnectError("DNS failure")
        with pytest.raises(MetadataResolveError, match="Crossref request failed"):
            resolve_doi("10.1/x")

    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_malformed_json_raises(self, mock_get: MagicMock) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.side_effect = ValueError("not json")
        mock_get.return_value = resp
        with pytest.raises(MetadataResolveError, match="invalid JSON"):
            resolve_doi("10.1/x")

    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_response_missing_message_raises(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, {"status": "ok"})
        with pytest.raises(MetadataResolveError, match="message"):
            resolve_doi("10.1/x")

    def test_empty_doi(self) -> None:
        with pytest.raises(MetadataResolveError, match="Empty DOI"):
            resolve_doi("  ")

    @patch.dict("os.environ", {"ZOT_CROSSREF_MAILTO": "test@example.com"})
    @patch("zotero_cli_cc.core.metadata_resolver.httpx.get")
    def test_mailto_added_to_user_agent(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, {"message": {"title": ["x"]}})
        resolve_doi("10.1/x")
        ua = mock_get.call_args.kwargs["headers"]["User-Agent"]
        assert "mailto:test@example.com" in ua
