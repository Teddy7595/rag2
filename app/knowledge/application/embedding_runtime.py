from __future__ import annotations

from functools import lru_cache
from hashlib import sha1
from math import sqrt
from pathlib import Path
import re
from typing import Any, cast


def _tokenize(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9áéíóúñ]+", text.lower()):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _normalize_vector(values: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [round(value / norm, 6) for value in values]


def _hash_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokenize(text):
        digest = sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    return _normalize_vector(vector)


class SemanticEmbeddingRuntime:
    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir
        self._model: object | None = None

    def available(self) -> bool:
        return self._resolve_model_dir() is not None and self._sentence_transformers_class() is not None

    def embed_text(self, text: str) -> list[float]:
        model = self._load_model()
        if model is None:
            return self.legacy_embed_text(text)

        try:
            encoded = cast(list[list[float]] | list[float] | Any, model.encode([text], normalize_embeddings=True))
        except Exception:
            return self.legacy_embed_text(text)

        if isinstance(encoded, list) and encoded and isinstance(encoded[0], list):
            return [float(value) for value in encoded[0]]
        if isinstance(encoded, list):
            return [float(value) for value in encoded]
        try:
            return [float(value) for value in encoded[0].tolist()]
        except Exception:
            return self.legacy_embed_text(text)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def classify_by_prototypes(
        self,
        text: str,
        prototypes: dict[str, tuple[str, ...] | list[str]],
        *,
        threshold: float = 0.24,
        margin: float = 0.03,
    ) -> str | None:
        if not prototypes:
            return None

        query_embedding = self.embed_text(text)
        if not query_embedding:
            return None

        ranked: list[tuple[str, float]] = []
        for label, samples in prototypes.items():
            sample_scores = [self.cosine_similarity(query_embedding, self.embed_text(sample)) for sample in samples if sample.strip()]
            if not sample_scores:
                continue
            ranked.append((label, sum(sample_scores) / len(sample_scores)))

        if not ranked:
            return None

        ranked.sort(key=lambda item: item[1], reverse=True)
        best_label, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if best_score < threshold or (best_score - second_score) < margin:
            return None
        return best_label

    @staticmethod
    def cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0

        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def legacy_embed_text(self, text: str) -> list[float]:
        return _hash_embedding(text)

    def _load_model(self) -> object | None:
        if self._model is not None:
            return self._model

        model_dir = self._resolve_model_dir()
        model_class = self._sentence_transformers_class()
        if model_dir is None or model_class is None:
            return None

        try:
            self._model = model_class(str(model_dir))
        except Exception:
            self._model = None
        return self._model

    def _resolve_model_dir(self) -> Path | None:
        if self.model_dir and self.model_dir.exists():
            return self.model_dir
        return None

    @staticmethod
    @lru_cache(maxsize=1)
    def _sentence_transformers_class() -> type | None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return None
        return SentenceTransformer


def build_default_embedding_runtime(project_root: Path) -> SemanticEmbeddingRuntime:
    return SemanticEmbeddingRuntime(project_root / "ai_models" / "embeddings" / "BAAI__bge-m3")
