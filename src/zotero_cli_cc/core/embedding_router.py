from __future__ import annotations

from collections.abc import Callable

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.embedding_provider import EmbeddingProvider
from zotero_cli_cc.core.providers.aliyun import AliyunProvider
from zotero_cli_cc.core.providers.jina import JinaProvider


class EmbeddingRouter:
    """Holds the single embedding provider selected by config.provider."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.provider: EmbeddingProvider | None = None

        api_key = config.api_key
        if not api_key:
            return
        if config.provider == "jina":
            jina_url = config.url if "jina" in config.url else "https://api.jina.ai/v1/embeddings"
            self.provider = JinaProvider(api_key=api_key, model=config.model, url=jina_url)
        elif config.provider == "aliyun":
            self.provider = AliyunProvider(
                api_key=api_key,
                model=config.model,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

    def embed(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        if self.provider is None:
            raise RuntimeError("No embedding provider configured")
        return self.provider.embed(texts, progress_callback)
