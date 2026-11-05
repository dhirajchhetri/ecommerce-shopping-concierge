"""Catalog search. Embeddings retrieve SKUs; prices and stock come from the record."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from kitline.catalog_data import PRODUCTS, Product
from kitline.embeddings import Embedder, HashingEmbedder
from kitline.vectorstore import LocalVectorStore, VectorStore


@dataclass
class SearchHit:
    sku: str
    name: str
    vendor: str
    category: str
    price_cents: int
    stock: int
    series: str
    score: float
    snippet: str

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["score"] = round(self.score, 4)
        return payload


class Catalog:
    def __init__(self, products: tuple[Product, ...] | list[Product], embedder: Embedder, store: VectorStore) -> None:
        # Copy so a caller can change a price without editing the module-level catalog.
        self.products = {product.sku: replace(product) for product in products}
        self.embedder = embedder
        self.store = store
        texts = [product.index_text() for product in self.products.values()]
        self.embedder.fit(texts)
        vectors = self.embedder.embed(texts)
        self.store.upsert(list(zip(self.products.keys(), vectors, strict=True)))

    @classmethod
    def create_default(cls) -> Catalog:
        embedder = HashingEmbedder()
        return cls(PRODUCTS, embedder, LocalVectorStore())

    def get(self, sku: str) -> Product | None:
        return self.products.get(sku)

    def search(self, query: str, category: str | None = None, limit: int = 6) -> list[SearchHit]:
        # Over-fetch so a category filter still has enough hits.
        raw = self.store.search(self.embedder.embed_one(query), k=max(limit * 4, limit))
        hits: list[SearchHit] = []
        for sku, score in raw:
            product = self.products.get(sku)
            if product is None:
                continue
            if category and product.category != category:
                continue
            hits.append(
                SearchHit(
                    sku=product.sku,
                    name=product.name,
                    vendor=product.vendor,
                    category=product.category,
                    price_cents=product.price_cents,
                    stock=product.stock,
                    series=product.series,
                    score=score,
                    snippet=product.description[:180],
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def all_products(self) -> list[Product]:
        return sorted(self.products.values(), key=lambda product: (product.category, product.price_cents, product.sku))
