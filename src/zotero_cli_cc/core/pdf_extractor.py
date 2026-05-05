from __future__ import annotations

import io
import os
import re
import sys
import time
import warnings
import zipfile
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

import pymupdf


class PdfExtractionError(Exception):
    """Raised when PDF text extraction fails."""

    pass


class BasePdfExtractor(ABC):
    """Abstract base class for PDF text/annotation extraction."""

    @abstractmethod
    def extract_text(self, pdf_path: Path, pages: tuple[int, int] | None = None) -> str:
        """Extract text from a PDF.

        Args:
            pdf_path: Path to the PDF file.
            pages: Optional (start, end) page tuple (1-indexed, inclusive).

        Returns:
            Extracted text, one page per line.
        """
        ...

    @abstractmethod
    def extract_annotations(self, pdf_path: Path) -> list[dict]:
        """Extract annotations (highlights, notes, comments) from a PDF.

        Returns:
            List of dicts with keys: type, page, content, quote (for highlights).
        """
        ...

    @abstractmethod
    def extract_doi(self, pdf_path: Path) -> str | None:
        """Extract DOI from first 2 pages of a PDF.

        Returns:
            First DOI match or None.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the extractor name (e.g. 'pymupdf')."""
        ...


class PyMuPdfExtractor(BasePdfExtractor):
    def __init__(self) -> None:
        self._pymupdf4llm_available: bool | None = None

    def _check_pymupdf4llm(self) -> bool:
        if self._pymupdf4llm_available is None:
            try:
                import pymupdf4llm  # type: ignore[import]  # noqa: F401

                self._pymupdf4llm_available = True
            except ImportError:
                self._pymupdf4llm_available = False
        return bool(self._pymupdf4llm_available)

    def extract_text(self, pdf_path: Path, pages: tuple[int, int] | None = None) -> str:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if self._check_pymupdf4llm():
            try:
                import pymupdf4llm  # type: ignore[import]

                if pages:
                    start, end = pages
                    md = pymupdf4llm.to_markdown(str(pdf_path), pages=list(range(start - 1, end)))
                else:
                    md = pymupdf4llm.to_markdown(str(pdf_path))
                return str(md)
            except Exception:
                pass

        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as e:
            raise type(e)(f"Cannot open PDF: {e}") from e
        try:
            if pages:
                start, end = pages
                if start > len(doc):
                    raise ValueError(f"Start page {start} exceeds document length ({len(doc)} pages)")
                page_range = range(start - 1, min(end, len(doc)))
            else:
                page_range = range(len(doc))
            texts = []
            for i in page_range:
                texts.append(doc[i].get_text())
            return "\n".join(texts)
        finally:
            doc.close()

    def extract_annotations(self, pdf_path: Path) -> list[dict]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as e:
            raise type(e)(f"Cannot open PDF: {e}") from e
        annotations: list[dict] = []
        try:
            for page_num, page in enumerate(doc, start=1):  # type: ignore[arg-type, var-annotated]
                for annot in page.annots() or []:
                    entry: dict = {
                        "type": annot.type[1],
                        "page": page_num,
                        "content": annot.info.get("content", "") or "",
                    }
                    if annot.type[0] in (8, 9, 10, 11):
                        try:
                            quads = annot.vertices
                            if quads:
                                quad_points = [pymupdf.Quad(quads[i : i + 4]) for i in range(0, len(quads), 4)]
                                text_parts = []
                                for q in quad_points:
                                    text_parts.append(page.get_text("text", clip=q.rect).strip())
                                quoted = " ".join(t for t in text_parts if t)
                                if quoted:
                                    entry["quote"] = quoted
                        except Exception:
                            pass
                    annotations.append(entry)
        finally:
            doc.close()
        return annotations

    def extract_doi(self, pdf_path: Path) -> str | None:
        try:
            text = self.extract_text(pdf_path, pages=(1, 2))
        except (FileNotFoundError, OSError):
            return None
        match = re.search(r"10\.\d{4,9}/[^\s]+", text)
        if match:
            return match.group(0).rstrip(".,;)]}>'\"")
        return None

    def name(self) -> str:
        return "pymupdf"


# ---------------------------------------------------------------------------
# MinerUExtractor - optional, may fail to import if 'requests' not installed
# ---------------------------------------------------------------------------

from requests import Session  # type: ignore[import-untyped]  # noqa: E402


class MinerUExtractor(BasePdfExtractor):
    _API_BASE = "https://mineru.net/api/v4"
    _RATE_LIMIT = 50
    _RATE_WINDOW = 60.0

    def __init__(self, config_token: str | None = None) -> None:
        self._session = Session()
        self._rate_limiter = _RateLimiter(self._RATE_LIMIT, self._RATE_WINDOW)
        self._token: str | None = None
        self._config_token = config_token

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = _load_token(self._config_token)
        return self._token

    def name(self) -> str:
        return "mineru"

    def extract_annotations(self, pdf_path: Path) -> list[dict]:
        return []

    def extract_doi(self, pdf_path: Path) -> str | None:
        return None

    def _upload_batch(
        self,
        files: list[tuple[Path, str, str]],
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[str, list[str]]:
        url = f"{self._API_BASE}/file-urls/batch"
        payload = {
            "files": [{"name": name, "data_id": data_id[:50]} for _, name, data_id in files],
            "model_version": "vlm",
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        self._rate_limiter.acquire()
        resp = _retry_with_backoff(lambda: self._session.post(url, json=payload, headers=headers, timeout=30))
        if resp.status_code != 200:
            raise PdfExtractionError(f"Failed to get upload URL: {resp.status_code} {resp.text}")
        resp_json = resp.json()
        data = resp_json["data"]
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls", [])
        if not batch_id or not file_urls:
            raise PdfExtractionError(f"Invalid response from file-urls/batch: {data}")

        for idx, ((pdf_path, _, _), upload_url) in enumerate(zip(files, file_urls)):
            self._rate_limiter.acquire()
            with open(pdf_path, "rb") as f:
                resp = _retry_with_backoff(
                    lambda: self._session.put(
                        upload_url,
                        data=f,
                        timeout=120,
                    )
                )
                if resp.status_code not in (200, 201):
                    raise PdfExtractionError(f"Failed to upload file: {resp.status_code} {resp.text}")
            if progress_callback:
                progress_callback(idx + 1)

        return batch_id, file_urls

    def _poll_batch_results(
        self,
        batch_id: str,
        expected_count: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, tuple[str, str, str]]:
        url = f"{self._API_BASE}/extract-results/batch/{batch_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        for _ in range(360):
            self._rate_limiter.acquire()
            resp = _retry_with_backoff(lambda: self._session.get(url, headers=headers, timeout=30))
            if resp.status_code != 200:
                raise PdfExtractionError(f"Failed to poll results: {resp.status_code} {resp.text}")
            result = resp.json()
            data = result.get("data", {})
            extract_results = data.get("extract_result", [])
            if not extract_results:
                raise PdfExtractionError(f"No extract_result in response: {result}")

            state_map: dict[str, tuple[str, str, str]] = {}
            pending_count = 0
            done_count = 0

            for item in extract_results:
                file_name = item.get("file_name", "")
                state = item.get("state", "")
                full_zip_url = item.get("full_zip_url") or ""
                err_msg = item.get("err_msg") or ""
                state_map[file_name] = (state, full_zip_url, err_msg)
                if state in ("waiting-file", "pending", "running"):
                    pending_count += 1
                elif state == "done":
                    done_count += 1

            if progress_callback:
                progress_callback(done_count, expected_count)

            if pending_count == 0:
                return state_map

            time.sleep(5)
        raise PdfExtractionError(
            f"Timeout waiting for MinerU extraction (360 polls). Pending files remain in batch {batch_id}"
        )

    def _poll_results(
        self,
        batch_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        state_map = self._poll_batch_results(batch_id, 1, progress_callback)
        item = next(iter(state_map.values()))
        state, full_zip_url, err_msg = item
        if state == "failed":
            raise PdfExtractionError(f"MinerU extraction failed: {err_msg}")
        if state != "done":
            raise PdfExtractionError(f"Unexpected state: {state}")
        if not full_zip_url:
            raise PdfExtractionError("No full_zip_url in completed response")
        return full_zip_url

    def _download_and_extract(
        self,
        zip_url: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        headers = {"Authorization": f"Bearer {self.token}"}
        self._rate_limiter.acquire()
        resp = _retry_with_backoff(lambda: self._session.get(zip_url, headers=headers, timeout=300, stream=True))
        if resp.status_code != 200:
            raise PdfExtractionError(f"Failed to download ZIP: {resp.status_code} {resp.text}")
        zip_data = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_data) as zf:
            if "full.md" not in zf.namelist():
                raise PdfExtractionError(f"full.md not found in ZIP: {zf.namelist()}")
            raw_md = zf.read("full.md").decode("utf-8", errors="replace")
        return _clean_markdown_images(raw_md)

    def _split_pdf(self, pdf_path: Path, max_pages: int) -> list[Path]:
        doc = pymupdf.open(str(pdf_path))
        total_pages = len(doc)
        chunks: list[Path] = []
        for start in range(0, total_pages, max_pages):
            chunk_path = pdf_path.with_suffix(f".chunk{start // max_pages}.pdf")
            chunk_doc = pymupdf.open()
            end = min(start + max_pages, total_pages)
            for page_num in range(start, end):
                chunk_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            chunk_doc.save(str(chunk_path))
            chunk_doc.close()
            chunks.append(chunk_path)
        doc.close()
        return chunks

    def _extract_single(
        self,
        pdf_path: Path,
        progress_callback: Callable[[str, int, int, int], None] | None = None,
    ) -> str:
        file_name = pdf_path.name
        data_id = os.path.splitext(file_name)[0]

        def upload_progress(done: int) -> None:
            if progress_callback:
                progress_callback("upload", done, 1, 0)

        batch_id, [zip_url] = self._upload_batch([(pdf_path, file_name, data_id)], upload_progress)

        def poll_progress(done: int, total: int) -> None:
            if progress_callback:
                progress_callback("process", done, total, 0)

        zip_url = self._poll_results(batch_id, poll_progress)

        def download_progress(done: int, total: int) -> None:
            if progress_callback:
                progress_callback("download", done, total, 0)

        return self._download_and_extract(zip_url, download_progress)

    def extract_text(
        self,
        pdf_path: Path,
        pages: tuple[int, int] | None = None,
        progress_callback: Callable[[str, int, int, int], None] | None = None,
    ) -> str:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        file_size = pdf_path.stat().st_size
        if file_size > 200 * 1024 * 1024:
            raise PdfExtractionError("PDF exceeds 200MB limit")

        doc = pymupdf.open(str(pdf_path))
        total_pages = len(doc)
        doc.close()

        if total_pages > 200:
            if pages:
                raise PdfExtractionError("Page range splitting not supported for PDFs >200 pages")
            chunk_paths = self._split_pdf(pdf_path, 200)
            total_chunks = len(chunk_paths)
            try:
                texts = []
                for chunk_idx, chunk_path in enumerate(chunk_paths, 1):
                    # Wrap progress_callback to report chunk progress instead of per-chunk-internal progress
                    if progress_callback is not None:

                        def make_wrapped_callback(
                            idx: int, original: Callable[[str, int, int, int], None]
                        ) -> Callable[[str, int, int, int], None]:
                            def wrapped(phase: str, current: int, total: int, pages: int) -> None:
                                original(phase, idx, total_chunks, pages)

                            return wrapped

                        wrapped_callback: Callable[[str, int, int, int], None] | None = make_wrapped_callback(
                            chunk_idx, progress_callback
                        )
                    else:
                        wrapped_callback = None
                    texts.append(self._extract_single(chunk_path, wrapped_callback))
                return "\n\n".join(texts)
            finally:
                for chunk_path in chunk_paths:
                    chunk_path.unlink(missing_ok=True)
        else:
            if pages:
                chunk_path = pdf_path.with_suffix(".pagetemp.pdf")
                doc = pymupdf.open(str(pdf_path))
                chunk_doc = pymupdf.open()
                start, end = pages
                for page_num in range(start - 1, min(end, total_pages)):
                    chunk_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                chunk_doc.save(str(chunk_path))
                chunk_doc.close()
                doc.close()
                try:
                    return self._extract_single(chunk_path, progress_callback)
                finally:
                    chunk_path.unlink(missing_ok=True)
            else:
                return self._extract_single(pdf_path, progress_callback)

    def extract_text_batch(
        self,
        pdf_paths: list[Path],
        progress_callback: Callable[[str, int, int, int], None] | None = None,
    ) -> dict[Path, str | Exception]:
        results: dict[Path, str | Exception] = {}
        temp_files: list[Path] = []
        original_to_chunks: dict[Path, list[Path]] = {}
        total_pages = 0

        def do_progress(phase: str, current: int, total: int, pages: int = 0) -> None:
            if progress_callback:
                progress_callback(phase, current, total, pages)

        valid_batch_args: list[tuple[Path, str, str]] = []
        validated_count = 0
        for pdf_path in pdf_paths:
            validated_count += 1
            do_progress("validate", validated_count, len(pdf_paths), total_pages)

            if not pdf_path.exists():
                results[pdf_path] = FileNotFoundError(f"PDF not found: {pdf_path}")
                continue

            file_size = pdf_path.stat().st_size
            if file_size > 200 * 1024 * 1024:
                results[pdf_path] = PdfExtractionError("PDF exceeds 200MB limit")
                continue

            doc = pymupdf.open(str(pdf_path))
            page_count = len(doc)
            doc.close()
            total_pages += page_count

            if page_count > 200:
                chunk_paths = self._split_pdf(pdf_path, 200)
                temp_files.extend(chunk_paths)
                original_to_chunks[pdf_path] = chunk_paths
                for chunk_path in chunk_paths:
                    file_name = chunk_path.name
                    data_id = os.path.splitext(pdf_path.name)[0] + f"_p{chunk_path.stem.split('chunk')[1]}"
                    valid_batch_args.append((chunk_path, file_name, data_id))
            else:
                original_to_chunks[pdf_path] = [pdf_path]
                file_name = pdf_path.name
                data_id = os.path.splitext(file_name)[0]
                valid_batch_args.append((pdf_path, file_name, data_id))

        total_chunks = len(valid_batch_args)

        upload_count = 0
        download_count = 0
        completed_count = 0

        for batch_idx, i in enumerate(range(0, len(valid_batch_args), 50)):
            batch = valid_batch_args[i : i + 50]

            def upload_progress(idx: int) -> None:
                nonlocal upload_count
                upload_count = i + idx
                do_progress("upload", upload_count, total_chunks, total_pages)

            batch_id, _ = self._upload_batch(batch, upload_progress)

            def poll_progress(done: int, _batch_total: int) -> None:
                nonlocal completed_count
                completed_count = done
                do_progress("process", completed_count, total_chunks, total_pages)

            state_map = self._poll_batch_results(batch_id, len(batch), poll_progress)

            for chunk_path, file_name, _ in batch:
                download_count += 1
                do_progress("download", download_count, total_chunks, total_pages)

                state, full_zip_url, err_msg = state_map.get(file_name, ("", "", ""))

                orig_for_chunk: Path | None = None
                for orig, chunks in original_to_chunks.items():
                    if chunk_path in chunks:
                        orig_for_chunk = orig
                        break

                if orig_for_chunk is None:
                    continue

                if state == "failed":
                    results[orig_for_chunk] = PdfExtractionError(f"MinerU extraction failed: {err_msg}")
                elif state == "done" and full_zip_url:
                    try:
                        text = self._download_and_extract(full_zip_url)
                        existing = results.get(orig_for_chunk)
                        if existing is None or isinstance(existing, Exception):
                            results[orig_for_chunk] = text
                        else:
                            results[orig_for_chunk] = existing + "\n\n" + text
                    except Exception as e:
                        results[orig_for_chunk] = e
                else:
                    results[orig_for_chunk] = PdfExtractionError(f"Unexpected state: {state}")

        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)

        return results


# ---------------------------------------------------------------------------
# Internal helpers (used by MinerUExtractor)
# ---------------------------------------------------------------------------


class _RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self._limit = limit
        self._window = window
        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.time()
                while self._timestamps and self._timestamps[0] <= now - self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._limit:
                    self._timestamps.append(time.time())
                    return
                sleep_time = self._timestamps[0] - (now - self._window)
            if sleep_time > 0:
                sys.stdout.write(f"\r{' ' * 60}\r    [rate-limit] sleeping {sleep_time:.1f}s")
                sys.stdout.flush()
                time.sleep(sleep_time)
                while self._timestamps and self._timestamps[0] <= now - self._window:
                    self._timestamps.popleft()


def _load_token(config_token: str | None = None) -> str:
    token = os.environ.get("MINERU_TOKEN")
    if token:
        return token
    token_path = Path.home() / ".config" / "mineru" / "token"
    if token_path.exists():
        return token_path.read_text().strip()
    if config_token:
        return config_token
    raise PdfExtractionError("MINERU_TOKEN not set and ~/.config/mineru/token not found")


def _retry_with_backoff(func: Any, *args: Any, **kwargs: Any) -> Any:
    for attempt in range(3):
        try:
            return func(*args, **kwargs)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 * (attempt + 1))
    raise


def _clean_markdown_images(text: str) -> str:
    return re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_EXTRACTORS: dict[str, type[BasePdfExtractor]] = {"pymupdf": PyMuPdfExtractor, "mineru": MinerUExtractor}


def get_extractor(name: str | None = None) -> BasePdfExtractor:
    """Factory to get a registered PDF extractor by name.

    Args:
        name: Extractor name (e.g. 'pymupdf'). If None, reads from config.

    Returns:
        An instance of the requested extractor.

    Raises:
        KeyError: If no extractor with the given name is registered.
    """
    if name is None:
        from zotero_cli_cc.config import load_pdf_config

        cfg = load_pdf_config()
        name = cfg.extractor
    extractor_cls = _EXTRACTORS[name]
    if name == "mineru":
        from zotero_cli_cc.config import load_pdf_config

        cfg = load_pdf_config()
        return extractor_cls(cfg.mineru_token)  # type: ignore[call-arg]
    return extractor_cls()


# ---------------------------------------------------------------------------
# Deprecated functions (kept for backwards compatibility)
# ---------------------------------------------------------------------------


def extract_text_from_pdf(
    pdf_path: Path,
    pages: tuple[int, int] | None = None,
) -> str:
    warnings.warn(
        "extract_text_from_pdf is deprecated, use PyMuPdfExtractor().extract_text or get_extractor('pymupdf')",
        DeprecationWarning,
        stacklevel=2,
    )
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise PdfExtractionError(f"Cannot open PDF: {e}") from e
    try:
        if pages:
            start, end = pages
            if start > len(doc):
                raise PdfExtractionError(f"Start page {start} exceeds document length ({len(doc)} pages)")
            page_range = range(start - 1, min(end, len(doc)))
        else:
            page_range = range(len(doc))
        texts = []
        for i in page_range:
            texts.append(doc[i].get_text())
        return "\n".join(texts)
    except PdfExtractionError:
        raise
    except Exception as e:
        raise PdfExtractionError(f"Failed to extract text: {e}") from e
    finally:
        doc.close()


def extract_annotations(pdf_path: Path) -> list[dict]:
    """Extract annotations (highlights, notes, comments) from a PDF.

    Returns list of dicts with keys: type, page, content, quote (for highlights).
    """
    warnings.warn(
        "extract_annotations is deprecated, use PyMuPdfExtractor().extract_annotations or get_extractor('pymupdf')",
        DeprecationWarning,
        stacklevel=2,
    )
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise PdfExtractionError(f"Cannot open PDF: {e}") from e
    annotations: list[dict] = []
    try:
        for page_num, page in enumerate(doc, start=1):  # type: ignore[var-annotated,arg-type]
            for annot in page.annots() or []:
                entry: dict = {
                    "type": annot.type[1],  # e.g. "Highlight", "Text", "Underline"
                    "page": page_num,
                    "content": annot.info.get("content", "") or "",
                }
                # For highlight/underline/squiggly/strikeout, extract quoted text
                if annot.type[0] in (8, 9, 10, 11):
                    try:
                        quads = annot.vertices
                        if quads:
                            quad_points = [pymupdf.Quad(quads[i : i + 4]) for i in range(0, len(quads), 4)]
                            text_parts = []
                            for q in quad_points:
                                text_parts.append(page.get_text("text", clip=q.rect).strip())
                            quoted = " ".join(t for t in text_parts if t)
                            if quoted:
                                entry["quote"] = quoted
                    except Exception:
                        pass
                annotations.append(entry)
    finally:
        doc.close()
    return annotations


def extract_doi(pdf_path: Path) -> str | None:
    """Extract DOI from first 2 pages of a PDF. Returns first match or None."""
    warnings.warn(
        "extract_doi is deprecated, use PyMuPdfExtractor().extract_doi or get_extractor('pymupdf')",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        text = extract_text_from_pdf(pdf_path, pages=(1, 2))
    except (PdfExtractionError, FileNotFoundError):
        return None
    match = re.search(r"10\.\d{4,9}/[^\s]+", text)
    if match:
        return match.group(0).rstrip(".,;)]}>'\"")
    return None
