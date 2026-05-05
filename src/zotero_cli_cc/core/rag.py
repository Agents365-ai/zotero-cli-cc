from __future__ import annotations

import json as json_mod
import math
import re
import urllib.request
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.pdf_cache import PdfCache
from zotero_cli_cc.core.pdf_extractor import get_extractor
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


def clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<td[^>]*>(.*?)</td>", r"\1\t", text, flags=re.IGNORECASE)
    text = re.sub(r"<th[^>]*>(.*?)</th>", r"\1\t", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<tr[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</table>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<table[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&apos;", "'", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunk_by_char(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    step = max_chars - overlap if overlap else max_chars
    result = []
    start = 0
    while start < len(text):
        end = start + max_chars if start + max_chars <= len(text) else len(text)
        result.append(text[start:end])
        start += step
    return result


def _chunk_by_word(text: str, max_chars: int, overlap: int) -> list[str]:
    words = text.split()
    result: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        word_len = len(word) + 1
        if word_len > max_chars:
            if current:
                result.append(" ".join(current))
                current = []
                current_len = 0
            result.extend(_chunk_by_char(word, max_chars, overlap))
        elif current_len + word_len > max_chars and current:
            result.append(" ".join(current))
            current = [word]
            current_len = word_len
        else:
            current.append(word)
            current_len += word_len
    if current:
        result.append(" ".join(current))
    return result


def _chunk_by_sentence(text: str, max_chars: int, overlap: int) -> list[str]:
    sentences = re.split(r"(?<=[。！？])|(?<=[.?!])\s+", text)
    result: list[str] = []
    current: list[str] = []
    current_len = 0
    for sent in sentences:
        sent_len = len(sent)
        if sent_len > max_chars:
            if current:
                result.append("".join(current))
                current = []
                current_len = 0
            result.extend(_chunk_by_word(sent, max_chars, overlap))
        elif current_len + sent_len > max_chars and current:
            result.append("".join(current))
            current = [sent]
            current_len = sent_len
        else:
            current.append(sent)
            current_len += sent_len
    if current:
        result.append("".join(current))
    return result


def cascade_chunk(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return _chunk_by_sentence(text, max_chars, overlap)


def chunk_text(text: str, paper_title: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    text = clean_html(text)
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_text = ""
    for line in text.split("\n"):
        if re.match(r"^#{1,3}\s+", line):
            if current_text.strip():
                sections.append((current_heading, current_text.strip()))
            current_heading = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_text = ""
        else:
            current_text += line + "\n"
    if current_text.strip():
        sections.append((current_heading, current_text.strip()))
    if not sections:
        sections = [("", text.strip())]

    chunks: list[str] = []
    max_chars = max_tokens * 4
    for heading, section_text in sections:
        prefix = f"[{paper_title} > {heading}] " if heading else f"[{paper_title}] "
        if len(section_text) <= max_chars:
            chunks.append(prefix + section_text)
        else:
            paragraphs = re.split(r"\n\n+", section_text)
            for para in paragraphs:
                if len(para) <= max_chars:
                    chunks.append(prefix + para)
                else:
                    sub_chunks = cascade_chunk(para, max_chars, overlap)
                    for sc in sub_chunks:
                        chunks.append(prefix + sc)
    return chunks if chunks else [f"[{paper_title}] {text.strip()}"]


def convert_pdf_to_text(
    pdf_path: Path,
    extractor_name: str = "pymupdf",
    progress_callback: Callable[[str, int, int, int], None] | None = None,
) -> str:
    cache = PdfCache()
    cached = cache.get(pdf_path, extractor_name)
    if cached is not None:
        return cached
    extractor = get_extractor(extractor_name)
    text = extractor.extract_text(pdf_path, progress_callback=progress_callback)  # type: ignore[call-arg]
    cache.put(pdf_path, extractor_name, text)
    return text


def convert_pdfs_to_text(
    pdf_paths: list[Path],
    extractor_name: str = "pymupdf",
    progress_callback: Callable[[str, int, int, int], None] | None = None,
) -> dict[Path, str | Exception]:
    cache = PdfCache()
    results: dict[Path, str | Exception] = {}
    uncached: list[Path] = []

    for pdf_path in pdf_paths:
        cached_text = cache.get(pdf_path, extractor_name)
        if cached_text is not None:
            results[pdf_path] = cached_text
        else:
            uncached.append(pdf_path)

    if not uncached:
        return results

    if extractor_name == "mineru" and len(uncached) > 1:
        extractor = get_extractor(extractor_name)
        if hasattr(extractor, "extract_text_batch"):  # type: ignore[reportAttributeAccessIssue]
            batch_results = extractor.extract_text_batch(uncached, progress_callback)  # type: ignore[reportAttributeAccessIssue]
            for path, text_or_err in batch_results.items():
                if isinstance(text_or_err, str):
                    cache.put(path, "mineru", text_or_err)
                results[path] = text_or_err
            return results

    total = len(uncached)
    for idx, pdf_path in enumerate(uncached, 1):
        if progress_callback:
            progress_callback("extract", idx, total, 0)
        try:
            text = convert_pdf_to_text(pdf_path, extractor_name, progress_callback)
            results[pdf_path] = text
        except Exception as e:
            results[pdf_path] = e

    return results


def bm25_score_chunks(
    index: RagIndex,
    query: str,
    progress_callback: Callable[[int, int], None] | None = None,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[int, float, dict]]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    total_docs = int(index.get_meta("total_docs") or "0")
    avg_dl = float(index.get_meta("avg_doc_len") or "1")
    if total_docs == 0:
        return []
    chunks = index.get_all_chunks()
    total_chunks = len(chunks)
    chunk_ids = [c["id"] for c in chunks]

    # Bulk fetch df for query terms (1 query instead of N queries)
    conn = index._conn
    placeholders = ",".join("?" * len(query_terms))
    df_rows = conn.execute(
        f"SELECT term, COUNT(DISTINCT chunk_id) as cnt FROM bm25_terms WHERE term IN ({placeholders}) GROUP BY term",
        query_terms,
    ).fetchall()
    df: dict[str, int] = {r["term"]: r["cnt"] for r in df_rows}

    # Pre-compute IDF for each query term (avoid re-computing per chunk)
    idf: dict[str, float] = {}
    for term in query_terms:
        dft = df.get(term, 0)
        idf[term] = math.log((total_docs - dft + 0.5) / (dft + 0.5) + 1)

    # Bulk fetch all term frequencies for all chunks (1 query)
    all_term_tfs = index.get_bm25_terms_bulk(chunk_ids)

    results: list[tuple[int, float, dict]] = []
    report_every = max(1, total_chunks // 50)
    for i, chunk in enumerate(chunks):
        chunk_id = chunk["id"]
        term_tfs = all_term_tfs.get(chunk_id, {})
        doc_len = chunk.get("doc_len", 0) or len(tokenize(chunk["content"]))
        score = 0.0
        for term in query_terms:
            dft = df.get(term, 0)
            if dft == 0:
                continue
            tf = term_tfs.get(term, 0.0)
            idf_val = idf[term]
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / avg_dl)
            score += idf_val * numerator / denominator
        if score > 0:
            results.append((chunk_id, score, chunk))
        if progress_callback and (i + 1) % report_every == 0:
            progress_callback(i + 1, total_chunks)
    if progress_callback:
        progress_callback(total_chunks, total_chunks)
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_score_chunks(
    index: RagIndex,
    query_embedding: list[float],
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[tuple[int, float, dict]]:
    embeddings = index.get_all_embeddings()
    total_emb = len(embeddings)
    chunks_by_id = {c["id"]: c for c in index.get_all_chunks()}
    results: list[tuple[int, float, dict]] = []
    for i, (chunk_id, vec) in enumerate(embeddings):
        score = cosine_similarity(query_embedding, vec)
        if chunk_id in chunks_by_id:
            results.append((chunk_id, score, chunks_by_id[chunk_id]))
        if progress_callback:
            progress_callback(i + 1, total_emb)
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


def embed_texts(
    texts: list[str],
    config: EmbeddingConfig,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[list[float]] | None:
    if not config.is_configured:
        return None
    all_embeddings: list[list[float]] = []
    batch_size = 64
    total = len(texts)
    for i in range(0, total, batch_size):
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
        if progress_callback:
            progress_callback(min(i + batch_size, total), total)
    return all_embeddings
