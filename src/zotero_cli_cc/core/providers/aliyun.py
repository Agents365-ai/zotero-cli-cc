from __future__ import annotations

import json as json_mod
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from zotero_cli_cc.core.embedding_provider import EmbeddingProvider


class AliyunProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v3",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        batch_size: int = 10,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.batch_size = batch_size
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return "aliyun"

    def embed(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        total = len(texts)
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            embeddings = self._embed_batch(batch)
            all_embeddings.extend(embeddings)
            if progress_callback:
                progress_callback(min(i + self.batch_size, total), total)
        return all_embeddings

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body = json_mod.dumps({"model": self.model, "input": batch}).encode()
        req = urllib.request.Request(f"{self.base_url}/embeddings", data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("User-Agent", "zot-cli/0.2.0")

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json_mod.loads(resp.read())
                embeddings_data = data.get("data") or []
                return [item["embedding"] for item in embeddings_data]
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 413:
                    return self._fallback_to_individual(batch)
                time.sleep(2**attempt)
            except urllib.error.URLError as e:
                last_error = e
                time.sleep(2**attempt)

        if last_error:
            raise RuntimeError(
                f"Aliyun embedding failed after {self.max_retries} retries: {last_error}"
            ) from last_error
        return []

    def _fallback_to_individual(self, batch: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in batch:
            try:
                body = json_mod.dumps({"model": self.model, "input": text}).encode()
                req = urllib.request.Request(f"{self.base_url}/embeddings", data=body)
                req.add_header("Content-Type", "application/json")
                req.add_header("Authorization", f"Bearer {self.api_key}")
                req.add_header("User-Agent", "zot-cli/0.2.0")
                with urllib.request.urlopen(req) as resp:
                    data = json_mod.loads(resp.read())
                embedding = data.get("data", [{}])[0].get("embedding")
                results.append(embedding if embedding else [])
            except Exception:
                results.append([])
        return results
