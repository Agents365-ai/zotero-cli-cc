from __future__ import annotations

import json as json_mod
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.pdf_cache import PdfCache
from zotero_cli_cc.core.rag_index import RagIndex


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in text.lower().split():
        word = re.sub(r"[.,;:!?()\"'\[\]{}]+$", "", word)
        word = re.sub(r"^[.,;:!?()\"'\[\]{}]+", "", word)
        if word:
            tokens.append(word)
    return tokens


def compute_term_frequencies(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens)
    if total == 0:
        return {}
    return {term: count / total for term, count in counts.items()}


def build_metadata_chunk(title: str, authors: str, abstract: str | None, tags: list[str]) -> str:
    parts = [f"Title: {title}", f"Authors: {authors}"]
    if abstract:
        parts.append(f"Abstract: {abstract}")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    return "\n".join(parts)


def chunk_text(text: str, paper_title: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_text = ""
    for line in text.split("\n"):
        if re.match(r"^#{2,3}\s+", line):
            if current_text.strip():
                sections.append((current_heading, current_text.strip()))
            current_heading = re.sub(r"^#{2,3}\s+", "", line).strip()
            current_text = ""
        else:
            current_text += line + "\n"
    if current_text.strip():
        sections.append((current_heading, current_text.strip()))
    if not sections:
        sections = [("", text.strip())]

    chunks: list[str] = []
    for heading, section_text in sections:
        prefix = f"[{paper_title} > {heading}] " if heading else f"[{paper_title}] "
        words = section_text.split()
        if len(words) <= max_tokens:
            chunks.append(prefix + section_text)
        else:
            paragraphs = re.split(r"\n\n+", section_text)
            current_chunk_words: list[str] = []
            for para in paragraphs:
                para_words = para.split()
                # If a single paragraph exceeds max_tokens, split it directly by words
                if len(para_words) > max_tokens:
                    # flush current buffer first
                    if current_chunk_words:
                        chunks.append(prefix + " ".join(current_chunk_words))
                        current_chunk_words = current_chunk_words[-overlap:] if overlap else []
                    i = 0
                    while i < len(para_words):
                        window = para_words[i : i + max_tokens]
                        chunks.append(prefix + " ".join(window))
                        i += max_tokens - overlap if overlap else max_tokens
                    continue
                if len(current_chunk_words) + len(para_words) > max_tokens and current_chunk_words:
                    chunks.append(prefix + " ".join(current_chunk_words))
                    current_chunk_words = current_chunk_words[-overlap:] if overlap else []
                current_chunk_words.extend(para_words)
            if current_chunk_words:
                chunks.append(prefix + " ".join(current_chunk_words))
    return chunks if chunks else [f"[{paper_title}] {text.strip()}"]


def convert_pdf_to_text(pdf_path: Path, cache: PdfCache | None = None) -> str:
    """Convert PDF to text. Uses cache if provided, pymupdf4llm if available, else plain extraction."""
    if cache is not None:
        cached = cache.get(pdf_path)
        if cached is not None:
            return cached
    try:
        import pymupdf4llm

        text: str = pymupdf4llm.to_markdown(str(pdf_path))
    except ImportError:
        from zotero_cli_cc.core.pdf_extractor import extract_text_from_pdf

        text = extract_text_from_pdf(pdf_path)
    if cache is not None:
        cache.put(pdf_path, text)
    return text


def bm25_score_chunks(index: RagIndex, query: str, k1: float = 1.5, b: float = 0.75) -> list[tuple[int, float, dict]]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    total_docs = int(index.get_meta("total_docs") or "0")
    avg_dl = float(index.get_meta("avg_doc_len") or "1")
    if total_docs == 0:
        return []
    chunks = index.get_all_chunks()
    conn = index._conn
    df: dict[str, int] = {}
    for term in query_terms:
        row = conn.execute("SELECT COUNT(DISTINCT chunk_id) as cnt FROM bm25_terms WHERE term = ?", (term,)).fetchone()
        df[term] = row["cnt"] if row else 0
    results: list[tuple[int, float, dict]] = []
    for chunk in chunks:
        chunk_id = chunk["id"]
        term_tfs = index.get_bm25_terms_for_chunk(chunk_id)
        doc_len = len(tokenize(chunk["content"]))
        score = 0.0
        for term in query_terms:
            if term not in df or df[term] == 0:
                continue
            tf = term_tfs.get(term, 0.0)
            idf = math.log((total_docs - df[term] + 0.5) / (df[term] + 0.5) + 1)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / avg_dl)
            score += idf * numerator / denominator
        if score > 0:
            results.append((chunk_id, score, chunk))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_score_chunks(index: RagIndex, query_embedding: list[float]) -> list[tuple[int, float, dict]]:
    embeddings = index.get_all_embeddings()
    chunks_by_id = {c["id"]: c for c in index.get_all_chunks()}
    results: list[tuple[int, float, dict]] = []
    for chunk_id, vec in embeddings:
        score = cosine_similarity(query_embedding, vec)
        if chunk_id in chunks_by_id:
            results.append((chunk_id, score, chunks_by_id[chunk_id]))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def reciprocal_rank_fusion(*rankings: list[tuple[int, float, dict]], k: int = 60) -> list[tuple[int, float, dict]]:
    scores: dict[int, float] = {}
    chunk_map: dict[int, dict] = {}
    for ranking in rankings:
        for rank, (chunk_id, _score, chunk) in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            chunk_map[chunk_id] = chunk
    results = [(cid, score, chunk_map[cid]) for cid, score in scores.items()]
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def embed_texts(texts: list[str], config: EmbeddingConfig) -> list[list[float]] | None:
    if not config.is_configured:
        return None
    all_embeddings: list[list[float]] = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        body = json_mod.dumps({"model": config.model, "input": batch}).encode()
        req = urllib.request.Request(config.url, data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {config.api_key}")
        req.add_header("User-Agent", "zot-cli/0.2.0")
        with urllib.request.urlopen(req) as resp:
            data = json_mod.loads(resp.read())
        for item in data["data"]:
            all_embeddings.append(item["embedding"])
    return all_embeddings
