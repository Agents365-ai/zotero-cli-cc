from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import (
    GrobidExtractor,
    PdfExtractionError,
    _parse_tei_fulltext,
    _parse_tei_header_doi,
    _parse_tei_references,
    get_extractor,
)

FIXTURES = Path(__file__).parent / "fixtures"

_NS = 'xmlns="http://www.tei-c.org/ns/1.0"'

REFERENCES_TEI = f"""<TEI {_NS}>
  <text><back><div><listBibl>
    <biblStruct>
      <analytic>
        <title level="a">Attention Is All You Need</title>
        <author><persName><forename>Ashish</forename><surname>Vaswani</surname></persName></author>
        <author><persName><forename>Noam</forename><surname>Shazeer</surname></persName></author>
      </analytic>
      <monogr>
        <title level="j">NeurIPS</title>
        <imprint><date type="published" when="2017">2017</date></imprint>
      </monogr>
      <idno type="DOI">10.5555/3295222.3295349</idno>
    </biblStruct>
    <biblStruct>
      <analytic><title level="a">A second paper</title></analytic>
      <monogr><imprint><date when="2021-06">June 2021</date></imprint></monogr>
    </biblStruct>
  </listBibl></div></back></text>
</TEI>"""

HEADER_TEI = f"""<TEI {_NS}>
  <teiHeader><fileDesc><sourceDesc><biblStruct>
    <idno type="DOI">10.1000/xyz123</idno>
  </biblStruct></sourceDesc></fileDesc></teiHeader>
</TEI>"""

FULLTEXT_TEI = f"""<TEI {_NS}>
  <text><body>
    <div><head>Introduction</head><p>First paragraph.</p><p>Second paragraph.</p></div>
  </body></text>
</TEI>"""


class TestTeiParsing:
    def test_references_parsed(self):
        refs = _parse_tei_references(REFERENCES_TEI)
        assert len(refs) == 2
        first = refs[0]
        assert first["title"] == "Attention Is All You Need"
        assert first["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
        assert first["year"] == "2017"
        assert first["journal"] == "NeurIPS"
        assert first["doi"] == "10.5555/3295222.3295349"

    def test_reference_year_from_partial_date(self):
        refs = _parse_tei_references(REFERENCES_TEI)
        assert refs[1]["year"] == "2021"
        assert refs[1]["authors"] == []

    def test_references_bad_xml_raises(self):
        with pytest.raises(PdfExtractionError):
            _parse_tei_references("<not-xml")

    def test_header_doi(self):
        assert _parse_tei_header_doi(HEADER_TEI) == "10.1000/xyz123"

    def test_header_doi_missing_returns_none(self):
        assert _parse_tei_header_doi(f"<TEI {_NS}></TEI>") is None

    def test_header_doi_bad_xml_returns_none(self):
        assert _parse_tei_header_doi("<nope") is None

    def test_fulltext_joins_heads_and_paragraphs(self):
        text = _parse_tei_fulltext(FULLTEXT_TEI)
        assert "Introduction" in text
        assert "First paragraph." in text
        assert "Second paragraph." in text


class TestGrobidExtractor:
    def setup_method(self):
        self.extractor = GrobidExtractor("http://localhost:8070")

    def test_name(self):
        assert self.extractor.name() == "grobid"

    def test_registered(self):
        assert isinstance(get_extractor("grobid"), GrobidExtractor)

    def test_annotations_empty(self):
        assert self.extractor.extract_annotations(FIXTURES / "test.pdf") == []

    def test_page_range_unsupported(self):
        with pytest.raises(PdfExtractionError):
            self.extractor.extract_text(FIXTURES / "test.pdf", pages=(1, 2))

    def test_base_url_trailing_slash_stripped(self):
        assert GrobidExtractor("http://localhost:8070/")._base_url == "http://localhost:8070"


class TestReferencesNotSupportedByOthers:
    def test_pdfium_references_raise(self):
        from zotero_cli_cc.core.pdf_extractor import PdfiumExtractor

        with pytest.raises(PdfExtractionError):
            PdfiumExtractor().extract_references(FIXTURES / "test.pdf")
