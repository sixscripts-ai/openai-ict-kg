from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

import httpx

EMBEDDING_DIM = 128


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    name: str

    def score(self, query: str, title: str, content: str, created_at: str) -> float: ...


@dataclass
class LocalDeterministicEmbedder:
    name: str = "local-deterministic-v1"
    dim: int = EMBEDDING_DIM

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = [tok.strip().lower() for tok in text.split() if tok.strip()]
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dim):
                vec[i] += (digest[i % len(digest)] / 255.0) - 0.5

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


@dataclass
class OllamaEmbedder:
    name: str = "ollama"
    model: str = "nomic-embed-text"
    base_url: str = "http://127.0.0.1:11434"

    def embed(self, text: str) -> list[float]:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            payload = response.json()
        return payload.get("embedding", [])


@dataclass
class GeminiEmbedder:
    name: str = "gemini"
    model: str = "models/text-embedding-004"
    api_key: str = ""

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY", "")

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/{self.model}:embedContent",
                params={"key": self.api_key},
                json={"content": {"parts": [{"text": text}]}, "taskType": "RETRIEVAL_DOCUMENT"},
            )
            response.raise_for_status()
            payload = response.json()
        return payload["embedding"]["values"]


@dataclass
class HybridReranker:
    name: str = "hybrid-reranker-v1"

    def score(self, query: str, title: str, content: str, created_at: str) -> float:
        lexical = lexical_overlap_score(query, f"{title} {content}")
        recency = recency_score(created_at)
        return (0.8 * lexical) + (0.2 * recency)


def get_embedding_provider() -> EmbeddingProvider:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    if provider == "ollama":
        return OllamaEmbedder(
            model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        )
    if provider == "gemini":
        return GeminiEmbedder(
            model=os.getenv("GEMINI_EMBED_MODEL", "models/text-embedding-004"),
            api_key=os.getenv("GEMINI_API_KEY", ""),
        )
    return LocalDeterministicEmbedder()


def get_reranker() -> Reranker:
    return HybridReranker()


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if len(a_list) != len(b_list) or not a_list:
        return 0.0

    dot = sum(x * y for x, y in zip(a_list, b_list))
    a_norm = math.sqrt(sum(x * x for x in a_list))
    b_norm = math.sqrt(sum(y * y for y in b_list))
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return dot / (a_norm * b_norm)


def lexical_overlap_score(query: str, content: str) -> float:
    q_tokens = {tok.lower() for tok in query.split() if tok.strip()}
    c_tokens = {tok.lower() for tok in content.split() if tok.strip()}
    if not q_tokens or not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / len(q_tokens)


def recency_score(created_at: str) -> float:
    try:
        ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - ts).days, 0)
    return 1.0 / (1.0 + (age_days / 30.0))


def encode_embedding(embedding: list[float]) -> str:
    return ",".join(f"{v:.8f}" for v in embedding)


def decode_embedding(raw: str) -> list[float]:
    return [float(v) for v in raw.split(",") if v]
