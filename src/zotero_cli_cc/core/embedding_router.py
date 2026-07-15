from __future__ import annotations

from collections.abc import Callable

from zotero_cli_cc.config import EmbeddingConfig
from zotero_cli_cc.core.embedding_provider import EmbeddingProvider
from zotero_cli_cc.core.providers.aliyun import AliyunProvider
from zotero_cli_cc.core.providers.jina import JinaProvider

_JINA_DEFAULT_URL = "https://api.jina.ai/v1/embeddings"
_ALIYUN_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class EmbeddingRouter:
    """Holds the single embedding provider selected by config.provider."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.provider: EmbeddingProvider | None = None

        api_key = config.api_key
        if not api_key:
            return
        if config.provider == "jina":
            jina_url = config.url if "jina" in config.url else _JINA_DEFAULT_URL
            self.provider = JinaProvider(api_key=api_key, model=config.model, url=jina_url)
        elif config.provider in ("aliyun", "openai"):
            # AliyunProvider speaks the standard OpenAI-compatible /embeddings
            # protocol, so it also serves any custom endpoint (Bailian
            # workspace URLs, LiteLLM, Ollama, vLLM, ...).
            if config.provider == "aliyun" and config.url == _JINA_DEFAULT_URL:
                base_url = _ALIYUN_DEFAULT_URL
            else:
                # Accept both a base URL and a full .../embeddings endpoint
                base_url = config.url.rstrip("/").removesuffix("/embeddings")
            self.provider = AliyunProvider(api_key=api_key, model=config.model, base_url=base_url)

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
