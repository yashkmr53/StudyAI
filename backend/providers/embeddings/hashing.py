"""Local hashing embedding provider (architecture §2 "local embeddings").

🟡 Simplified local embedder: feature hashing over word unigrams+bigrams
into a fixed-dimension L2-normalized vector. Deterministic, dependency-
free, and genuinely lexical — good enough to exercise hybrid retrieval
end-to-end until a proper local model (e.g., bge-small via
sentence-transformers) is adopted (decision F-001).
"""
import hashlib
import math
import re

from providers.base import EmbeddingProvider

_TOKEN = re.compile(r"[a-z0-9]+")
_DIM = None  # set via configure()


def _dim() -> int:
    from django.conf import settings

    return int(getattr(settings, "EMBEDDING_DIMENSIONS", 384))


def _bucket(token: str) -> int:
    digest = hashlib.md5(token.encode()).digest()
    return int.from_bytes(digest[:4], "little") % _dim()


def _sign(token: str) -> float:
    digest = hashlib.md5(("s:" + token).encode()).digest()
    return 1.0 if digest[0] % 2 == 0 else -1.0


class HashingEmbeddingProvider:
    name = "hashing"
    
    @property
    def dimension(self) -> int:
        return 384
    
    @property
    def model_name(self) -> str:
        return "hashing"
    
    @property
    def model_version(self) -> str:
        return "hashing-384-v1"

    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]:
        dim = _dim()
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dim
            tokens = _TOKEN.findall(text.lower())
            grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            for g in grams:
                vec[_bucket(g)] += _sign(g)
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([round(v / norm, 6) for v in vec])
        return vectors
