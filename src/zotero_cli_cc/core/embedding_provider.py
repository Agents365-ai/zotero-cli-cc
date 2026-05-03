from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def embed(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        ...