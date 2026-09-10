from __future__ import annotations

import asyncio
import hashlib
import math
import struct
from typing import Protocol

from windops_backend.config import Settings

EMBEDDING_DIMENSIONS = 1536
# text-embedding-3-small accepts a much larger token window, but keeping each
# request near 3k tokens leaves room for non-ASCII tokenization and provider
# envelope differences.  The body extractor has a separate document limit.
EMBEDDING_MAX_INPUT_CHARACTERS = 12_000
EMBEDDING_CHUNK_OVERLAP_CHARACTERS = 1_000
MAX_EMBEDDING_CHUNKS_PER_DOCUMENT = 512
MAX_QUERY_AUTO_INDEX_DOCUMENTS = 8


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    production_ready: bool

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicTestEmbeddingProvider:
    """Offline-only embedding used by tests; never represented as production RAG."""

    provider_name = "deterministic_test"
    model_name = "sha256-token-projection-v1"
    production_ready = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_embedding(text) for text in texts]


class LiteLLMEmbeddingProvider:
    """Production embedding adapter with provider-reported vectors via LiteLLM."""

    provider_name = "litellm"
    production_ready = True

    def __init__(self, model: str) -> None:
        if not model.strip():
            raise ValueError("an explicit embedding model is required")
        self.model_name = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        response = await litellm.aembedding(model=self.model_name, input=texts)
        ordered = sorted(response.data, key=lambda item: int(item["index"]))
        vectors = [list(map(float, item["embedding"])) for item in ordered]
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise RuntimeError(
                f"embedding model {self.model_name} must return {EMBEDDING_DIMENSIONS} dimensions"
            )
        return vectors


def chunk_embedding_text(title: str, body: str) -> list[str]:
    """Split one document into bounded, overlapping model inputs."""

    title_prefix = title.strip()
    normalized_body = body.strip()
    if not title_prefix and not normalized_body:
        raise ValueError("knowledge document has no text to embed")

    prefix = f"{title_prefix}\n" if title_prefix and normalized_body else title_prefix
    available_body_characters = EMBEDDING_MAX_INPUT_CHARACTERS - len(prefix)
    if available_body_characters <= EMBEDDING_CHUNK_OVERLAP_CHARACTERS:
        raise ValueError("knowledge document title leaves no room for an embedding chunk")
    if not normalized_body:
        return [prefix[:EMBEDDING_MAX_INPUT_CHARACTERS]]
    if len(normalized_body) <= available_body_characters:
        return [f"{prefix}{normalized_body}"]

    chunks: list[str] = []
    start = 0
    while start < len(normalized_body):
        end = min(start + available_body_characters, len(normalized_body))
        chunks.append(f"{prefix}{normalized_body[start:end]}")
        if len(chunks) > MAX_EMBEDDING_CHUNKS_PER_DOCUMENT:
            raise ValueError(
                "knowledge document exceeds the maximum number of safe embedding chunks"
            )
        if end == len(normalized_body):
            break
        start = end - EMBEDDING_CHUNK_OVERLAP_CHARACTERS
    return chunks


async def embed_texts_with_controls(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    settings: Settings,
) -> list[list[float]]:
    """Embed bounded batches with a timeout and finite retry budget."""

    if not texts:
        return []
    if any(len(text) > EMBEDDING_MAX_INPUT_CHARACTERS for text in texts):
        raise ValueError("embedding input exceeds the configured model input limit")

    vectors: list[list[float]] = []
    for start in range(0, len(texts), settings.embedding_batch_size):
        batch = texts[start : start + settings.embedding_batch_size]
        batch_vectors: list[list[float]] | None = None
        for attempt in range(settings.embedding_max_retries + 1):
            try:
                async with asyncio.timeout(settings.embedding_timeout_seconds):
                    candidate_vectors = await provider.embed(batch)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= settings.embedding_max_retries:
                    raise RuntimeError(
                        f"embedding batch failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(min(0.25 * (2**attempt), 2.0))
                continue

            if len(candidate_vectors) != len(batch):
                raise RuntimeError(
                    f"embedding provider returned {len(candidate_vectors)} vectors; "
                    f"expected {len(batch)}"
                )
            batch_vectors = []
            for vector in candidate_vectors:
                if len(vector) != EMBEDDING_DIMENSIONS:
                    raise RuntimeError(
                        f"embedding provider returned {len(vector)} dimensions; "
                        f"expected {EMBEDDING_DIMENSIONS}"
                    )
                batch_vectors.append([float(value) for value in vector])
            break
        if batch_vectors is None:  # pragma: no cover - retry loop always raises or succeeds
            raise RuntimeError("embedding batch did not return vectors")
        vectors.extend(batch_vectors)
    return vectors


def aggregate_embedding_vectors(vectors: list[list[float]]) -> list[float]:
    """Store one normalized document vector while indexing many passages."""

    if not vectors:
        raise ValueError("cannot aggregate an empty embedding result")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise RuntimeError("embedding vectors cannot be aggregated with mixed dimensions")
    aggregate = [0.0] * EMBEDDING_DIMENSIONS
    for vector in vectors:
        for index, value in enumerate(vector):
            aggregate[index] += value
    norm = math.sqrt(sum(value * value for value in aggregate)) or 1.0
    return [value / norm for value in aggregate]


def _deterministic_embedding(text: str) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    tokens = [token for token in text.lower().replace("_", " ").split() if token]
    for token in tokens or [text.lower()]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        values[index] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def pack_embedding_vector(vector: list[float]) -> bytes:
    return struct.pack(f"!{len(vector)}f", *vector)


def _unpack_vector(value: bytes) -> list[float]:
    return list(struct.unpack(f"!{len(value) // 4}f", value))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _citation_href(uri: str, minio_public_base: str) -> str:
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    if uri.startswith("minio://"):
        return f"{minio_public_base.rstrip('/')}/{uri.removeprefix('minio://')}"
    if uri.startswith("windops://knowledge/documents/"):
        document_id = uri.removeprefix("windops://knowledge/documents/")
        return f"/api/v1/knowledge/documents/{document_id}"
    return uri
