"""Tests for RAG engine and index."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.rag import (
    bm25_score_chunks,
    build_metadata_chunk,
    chunk_text,
    compute_term_frequencies,
    cosine_similarity,
    embed_texts,
    reciprocal_rank_fusion,
    tokenize,
)
from zotero_cli_cc.core.rag_index import RagIndex


class TestRagIndex:
    def test_create_index(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            assert (tmp_path / "test.idx.sqlite").exists()
        finally:
            idx.close()

    def test_insert_and_get_chunks(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            idx.insert_chunk("ABC123", "metadata", "Title: Test Paper\nAbstract: about attention")
            idx.insert_chunk("ABC123", "pdf", "[Test Paper > Introduction] We study attention...")
            chunks = idx.get_all_chunks()
            assert len(chunks) == 2
            assert chunks[0]["item_key"] == "ABC123"
            assert chunks[0]["source"] == "metadata"
        finally:
            idx.close()

    def test_insert_bm25_terms(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            chunk_id = idx.insert_chunk("ABC123", "metadata", "attention mechanism")
            idx.insert_bm25_terms(chunk_id, {"attention": 1.0, "mechanism": 1.0})
            terms = idx.get_bm25_terms_for_chunk(chunk_id)
            assert "attention" in terms
        finally:
            idx.close()

    def test_set_and_get_meta(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            idx.set_meta("chunk_count", "42")
            idx.set_meta("has_embeddings", "false")
            assert idx.get_meta("chunk_count") == "42"
            assert idx.get_meta("has_embeddings") == "false"
            assert idx.get_meta("nonexistent") is None
        finally:
            idx.close()

    def test_insert_embedding(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            chunk_id = idx.insert_chunk("ABC123", "pdf", "some text")
            embedding = [0.1, 0.2, 0.3]
            idx.set_embedding(chunk_id, embedding)
            loaded = idx.get_embedding(chunk_id)
            assert len(loaded) == 3
            assert abs(loaded[0] - 0.1) < 1e-6
        finally:
            idx.close()

    def test_clear_index(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            idx.insert_chunk("ABC123", "metadata", "test")
            idx.clear()
            assert len(idx.get_all_chunks()) == 0
        finally:
            idx.close()

    def test_get_indexed_keys(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            idx.insert_chunk("ABC123", "metadata", "text a")
            idx.insert_chunk("DEF456", "metadata", "text b")
            idx.insert_chunk("ABC123", "pdf", "text c")
            keys = idx.get_indexed_keys()
            assert keys == {"ABC123", "DEF456"}
        finally:
            idx.close()


class TestTokenizer:
    def test_basic(self):
        assert tokenize("Hello World") == ["hello", "world"]

    def test_punctuation(self):
        assert tokenize("attention-based, model.") == ["attention-based", "model"]

    def test_empty(self):
        assert tokenize("") == []

    def test_numbers(self):
        assert tokenize("GPT-4 has 1.7T params") == ["gpt-4", "has", "1.7t", "params"]


class TestChunking:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Short text.", "Paper Title", max_tokens=500)
        assert len(chunks) == 1
        assert "Short text." in chunks[0]

    def test_heading_split(self):
        text = "## Introduction\nSome intro text here.\n\n## Methods\nSome methods text here."
        chunks = chunk_text(text, "Paper", max_tokens=500)
        assert len(chunks) == 2

    def test_long_section_paragraph_split(self):
        long_para = "word " * 600
        text = f"## Section\n{long_para}"
        chunks = chunk_text(text, "Paper", max_tokens=500)
        assert len(chunks) >= 2

    def test_chunk_prefix(self):
        text = "## Introduction\nSome text here."
        chunks = chunk_text(text, "My Paper", max_tokens=500)
        assert "[My Paper > Introduction]" in chunks[0]

    def test_metadata_chunk(self):
        chunk = build_metadata_chunk(
            title="Attention Is All You Need",
            authors="Vaswani et al.",
            abstract="We propose a new architecture...",
            tags=["transformer", "attention"],
        )
        assert "Attention Is All You Need" in chunk
        assert "Vaswani et al." in chunk
        assert "transformer" in chunk


class TestBM25:
    def test_term_frequencies(self):
        tfs = compute_term_frequencies(["the", "cat", "sat", "the"])
        assert tfs["the"] == pytest.approx(2 / 4)
        assert tfs["cat"] == pytest.approx(1 / 4)

    def test_bm25_scoring(self, tmp_path):
        idx = RagIndex(tmp_path / "test.idx.sqlite")
        try:
            c1 = idx.insert_chunk("A", "pdf", "attention mechanism in transformers")
            c2 = idx.insert_chunk("B", "pdf", "convolutional neural network for images")
            tfs1 = compute_term_frequencies(tokenize("attention mechanism in transformers"))
            tfs2 = compute_term_frequencies(tokenize("convolutional neural network for images"))
            idx.insert_bm25_terms(c1, tfs1)
            idx.insert_bm25_terms(c2, tfs2)
            idx.set_meta("total_docs", "2")
            idx.set_meta("avg_doc_len", "4")

            results = bm25_score_chunks(idx, "attention mechanism")
            assert len(results) > 0
            assert results[0][0] == c1
            assert results[0][1] > 0
        finally:
            idx.close()


class TestEmbedding:
    def test_cosine_similarity_identical(self):
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self):
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_embed_texts_not_configured(self):
        cfg = EmbeddingConfig(url="", api_key="", model="")
        result = embed_texts(["hello"], cfg)
        assert result is None

    def test_embed_texts_api_call(self):
        cfg = EmbeddingConfig(url="http://test/v1/embeddings", api_key="key", model="model", provider="aliyun")
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = embed_texts(["hello world"], cfg)
            assert result is not None
            assert len(result) == 1
            assert result[0] == [0.1, 0.2, 0.3]
            call_args = mock_urlopen.call_args[0][0]
            body = json.loads(call_args.data)
            assert body["model"] == "model"
            assert body["input"] == ["hello world"]


class TestRRF:
    def test_reciprocal_rank_fusion(self):
        ranking1 = [(1, 0.9, {"id": 1}), (2, 0.8, {"id": 2}), (3, 0.7, {"id": 3})]
        ranking2 = [(3, 0.95, {"id": 3}), (1, 0.85, {"id": 1}), (2, 0.5, {"id": 2})]
        fused = reciprocal_rank_fusion(ranking1, ranking2)
        # All 3 items should be present
        ids = [cid for cid, _, _ in fused]
        assert set(ids) == {1, 2, 3}
        # Item 1 and 3 should be top (both appear high in both rankings)
        assert ids[0] in (1, 3)
