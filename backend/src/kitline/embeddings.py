"""Local hashing embedder, and an optional Bedrock Titan embedder.

The local embedder is feature hashing with an idf weight fit on the catalog.
It is deterministic and has no network dependency. It is not a substitute for
a trained embedding model: collisions are expected, and retrieval quality on
this small catalog is checked with tests rather than claimed as a benchmark.

Amazon Titan Text Embeddings v2 is used only when KITLINE_EMBEDDINGS=bedrock.
That path needs AWS credentials and model access.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _bucket(token: str, dim: int) -> tuple[int, int]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "little") % dim
    sign = 1 if digest[4] % 2 == 0 else -1
    return index, sign


class Embedder(Protocol):
    dim: int

    def fit(self, texts: list[str]) -> None: ...

    def embed_one(self, text: str) -> list[float]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Signed feature hashing. Vectors are L2-normalized."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> None:
        doc_count = max(len(texts), 1)
        df: Counter[str] = Counter()
        for text in texts:
            df.update(set(tokenize(text)))
        self._idf = {token: math.log((1 + doc_count) / (1 + count)) + 1.0 for token, count in df.items()}

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        counts = Counter(tokenize(text))
        if not counts:
            return vector
        for token, tf in counts.items():
            weight = (1.0 + math.log(tf)) * self._idf.get(token, 1.0)
            index, sign = _bucket(token, self.dim)
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


class BedrockEmbedder:
    """Titan Text Embeddings v2. fit() is a no-op; the model is already trained."""

    def __init__(self, region: str, model_id: str = "amazon.titan-embed-text-v2:0", dim: int = 256) -> None:
        self.dim = dim
        self.region = region
        self.model_id = model_id
        self._client = None

    def fit(self, texts: list[str]) -> None:
        return None

    def _runtime(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def embed_one(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True})
        response = self._runtime().invoke_model(modelId=self.model_id, body=body)
        payload = json.loads(response["body"].read())
        vector = payload["embedding"]
        if len(vector) != self.dim:
            raise RuntimeError(f"Titan returned {len(vector)} dimensions, expected {self.dim}.")
        return [float(value) for value in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]
