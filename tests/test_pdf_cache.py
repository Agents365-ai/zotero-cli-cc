import time
from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_cache import PdfCache


@pytest.fixture
def cache(tmp_path):
    return PdfCache(tmp_path / "pdf_cache.sqlite")


def test_cache_miss(cache, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"fake pdf")
    assert cache.get(pdf) is None


def test_cache_put_and_get(cache, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"fake pdf")
    cache.put(pdf, "extracted text content")
    assert cache.get(pdf) == "extracted text content"


def test_cache_invalidation_on_mtime_change(cache, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"fake pdf v1")
    cache.put(pdf, "v1 text")
    time.sleep(0.05)
    pdf.write_bytes(b"fake pdf v2")
    assert cache.get(pdf) is None


def test_cache_clear(cache, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"fake pdf")
    cache.put(pdf, "text")
    cache.clear()
    assert cache.get(pdf) is None


def test_cache_stats(cache, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf1.write_bytes(b"a")
    pdf2 = tmp_path / "b.pdf"
    pdf2.write_bytes(b"b")
    cache.put(pdf1, "text a")
    cache.put(pdf2, "text b")
    stats = cache.stats()
    assert stats["entries"] == 2
    assert stats["total_chars"] > 0
