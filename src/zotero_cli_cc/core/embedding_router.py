from __future__ import annotations

from typing import Callable

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.embedding_provider import EmbeddingProvider
from zotero_cli_cc.core.providers.aliyun import AliyunProvider
from zotero_cli_cc.core.providers.jina import JinaProvider


class EmbeddingRouter:
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.providers: dict[str, EmbeddingProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        api_key = self.config.api_key
        model = self.config.model

        if self.config.provider in ("jina", "auto") and api_key:
            jina_url = self.config.url if "jina" in self.config.url else "https://api.jina.ai/v1/embeddings"
            self.providers["jina"] = JinaProvider(
                api_key=api_key,
                model=model,
                url=jina_url,
            )

        if self.config.provider in ("aliyun", "auto") and api_key:
            aliyun_key = self.config.aliyun_api_key or api_key
            aliyun_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            self.providers["aliyun"] = AliyunProvider(
                api_key=aliyun_key,
                model=model,
                base_url=aliyun_url,
            )

    def embed(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        provider = self._find_provider()
        if provider:
            return provider.embed(texts, progress_callback)

        raise RuntimeError("No embedding provider configured")

    def _find_provider(self) -> EmbeddingProvider | None:
        priority = ["aliyun", "jina"]
        for name in priority:
            if name in self.providers:
                return self.providers[name]
        return None