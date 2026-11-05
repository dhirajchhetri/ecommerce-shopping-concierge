"""Wire settings to a catalog, a model, a session store, and the service."""

from __future__ import annotations

import os

from kitline.catalog import Catalog
from kitline.catalog_data import PRODUCTS
from kitline.config import Settings
from kitline.embeddings import BedrockEmbedder, HashingEmbedder
from kitline.service import ConciergeService
from kitline.sessions import DynamoSessionStore, FileSessionStore, MemorySessionStore, SessionStore
from kitline.stub_model import StubModel
from kitline.vectorstore import LocalVectorStore, OpenSearchVectorStore, PgVectorStore


def build_service(settings: Settings) -> ConciergeService:
    if settings.embeddings == "bedrock":
        embedder = BedrockEmbedder(region=_region(settings))
    else:
        embedder = HashingEmbedder()

    if settings.vector_store == "pgvector":
        if not settings.database_url:
            raise RuntimeError("KITLINE_DATABASE_URL is required when KITLINE_VECTOR_STORE=pgvector.")
        store = PgVectorStore(settings.database_url, embedder.dim)
    elif settings.vector_store == "opensearch":
        if not settings.opensearch_endpoint:
            raise RuntimeError("KITLINE_OPENSEARCH_ENDPOINT is required when KITLINE_VECTOR_STORE=opensearch.")
        store = OpenSearchVectorStore(
            settings.opensearch_endpoint,
            _region(settings),
            settings.opensearch_index,
            embedder.dim,
        )
    else:
        store = LocalVectorStore()

    catalog = Catalog(PRODUCTS, embedder, store)
    return ConciergeService(
        catalog,
        _sessions(settings),
        _model(settings),
        max_attempts=settings.max_attempts,
    )


def _region(settings: Settings) -> str:
    return os.environ.get("AWS_REGION") or settings.aws_region


def _sessions(settings: Settings) -> SessionStore:
    if settings.session_store == "dynamodb":
        return DynamoSessionStore(settings.session_table, _region(settings))
    if settings.session_store == "file":
        return FileSessionStore(settings.session_dir)
    return MemorySessionStore()


def _model(settings: Settings):
    if settings.mode == "offline":
        return StubModel(fault=settings.stub_fault)
    from strands.models import BedrockModel

    return BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.bedrock_region,
        temperature=0.2,
        max_tokens=4096,
    )
