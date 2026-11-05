"""Vector indexes for catalog retrieval.

The in-process store is the offline default. Pgvector and OpenSearch Serverless
are available when those services are configured. All three return SKUs; the
catalog record is read afterwards so price and stock stay current.
"""

from __future__ import annotations

import json
import math
from typing import Protocol


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


class VectorStore(Protocol):
    def upsert(self, items: list[tuple[str, list[float]]]) -> None: ...

    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]: ...


class LocalVectorStore:
    def __init__(self) -> None:
        self._items: list[tuple[str, list[float]]] = []

    def upsert(self, items: list[tuple[str, list[float]]]) -> None:
        self._items = list(items)

    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        scored = [(sku, cosine(vector, stored)) for sku, stored in self._items]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:k]


def vector_literal(vector: list[float]) -> str:
    """pgvector text input. Values are already floats we produced."""
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


PG_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS kitline_products (
    sku text PRIMARY KEY,
    embedding vector({dim}) NOT NULL
);
"""

PG_SEARCH_SQL = """
SELECT sku, 1 - (embedding <=> %(query)s::vector) AS score
FROM kitline_products
ORDER BY embedding <=> %(query)s::vector
LIMIT %(k)s
"""


class PgVectorStore:
    """Postgres + pgvector. Requires the `stores` extra and a reachable database."""

    def __init__(self, dsn: str, dim: int) -> None:
        self.dsn = dsn
        self.dim = dim

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is not installed. Install kitline[stores].") from exc
        return psycopg.connect(self.dsn)

    def ensure_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(PG_SCHEMA_SQL.format(dim=int(self.dim)))
            conn.commit()

    def upsert(self, items: list[tuple[str, list[float]]]) -> None:
        self.ensure_schema()
        with self._connect() as conn, conn.cursor() as cur:
            for sku, vector in items:
                if len(vector) != self.dim:
                    raise ValueError(f"{sku} has {len(vector)} dimensions, expected {self.dim}.")
                cur.execute(
                    """
                    INSERT INTO kitline_products (sku, embedding)
                    VALUES (%s, %s::vector)
                    ON CONFLICT (sku) DO UPDATE SET embedding = EXCLUDED.embedding
                    """,
                    (sku, vector_literal(vector)),
                )
            conn.commit()

    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(PG_SEARCH_SQL, {"query": vector_literal(vector), "k": k})
            rows = cur.fetchall()
        return [(str(sku), float(score)) for sku, score in rows]


def knn_body(vector: list[float], k: int) -> dict:
    """OpenSearch k-NN query body."""
    return {
        "size": k,
        "query": {"knn": {"embedding": {"vector": vector, "k": k}}},
    }


def index_mapping(dim: int) -> dict:
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "sku": {"type": "keyword"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": dim,
                    "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib"},
                },
            }
        },
    }


class OpenSearchVectorStore:
    """Amazon OpenSearch Serverless vector collection, signed with SigV4.

    The collection and the data-access policy are created by the CDK stack.
    This client only writes vectors and runs k-NN search.
    """

    def __init__(self, endpoint: str, region: str, index: str, dim: int) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.region = region
        self.index = index
        self.dim = dim
        self._client = None

    def _opensearch(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
        except ImportError as exc:
            raise RuntimeError("opensearch-py is not installed. Install kitline[stores].") from exc
        host = self.endpoint.removeprefix("https://").removeprefix("http://")
        credentials = boto3.Session().get_credentials()
        if credentials is None:
            raise RuntimeError("No AWS credentials available for OpenSearch Serverless.")
        auth = AWSV4SignerAuth(credentials, self.region, "aoss")
        self._client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        return self._client

    def ensure_index(self) -> None:
        client = self._opensearch()
        if client.indices.exists(index=self.index):
            return
        client.indices.create(index=self.index, body=index_mapping(self.dim))

    def upsert(self, items: list[tuple[str, list[float]]]) -> None:
        self.ensure_index()
        client = self._opensearch()
        for sku, vector in items:
            client.index(index=self.index, id=sku, body={"sku": sku, "embedding": vector})

    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        client = self._opensearch()
        response = client.search(index=self.index, body=knn_body(vector, k))
        hits = response.get("hits", {}).get("hits", [])
        found: list[tuple[str, float]] = []
        for hit in hits:
            source = hit.get("_source", {})
            sku = source.get("sku") or hit.get("_id")
            score = float(hit.get("_score") or 0.0)
            if sku:
                found.append((str(sku), score))
        return found


def dump_vectors(items: list[tuple[str, list[float]]]) -> str:
    """Small helper used by tests to confirm vectors are JSON-safe."""
    return json.dumps([{"sku": sku, "dim": len(vector)} for sku, vector in items])


def l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))
