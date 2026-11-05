import pytest

from kitline.catalog_data import PRODUCTS


def test_catalog_is_synthetic_and_well_formed():
    skus = [product.sku for product in PRODUCTS]
    assert len(skus) == len(set(skus))
    assert len(PRODUCTS) >= 12
    vendors = {product.vendor for product in PRODUCTS}
    assert vendors == {"Northstar", "Pixelwell", "Harbor"}
    for product in PRODUCTS:
        assert product.price_cents > 0
        assert product.stock >= 0
        assert product.description
    out_of_stock = [product for product in PRODUCTS if product.stock == 0]
    assert out_of_stock, "the catalog includes an out-of-stock item for the stock check"


def test_search_finds_a_video_editing_laptop(catalog):
    hits = catalog.search("laptop for video editing and color grading", category="laptop", limit=3)
    assert hits
    assert hits[0].category == "laptop"
    assert hits[0].stock > 0
    assert hits[0].sku in {"NS-PRO-16", "HB-STUDIO-16"}


def test_search_hydrates_live_price(catalog):
    catalog.get("PW-SLIM-14").price_cents = 50_000
    hits = catalog.search("student laptop", category="laptop", limit=4)
    slim = next(hit for hit in hits if hit.sku == "PW-SLIM-14")
    assert slim.price_cents == 50_000


def test_embeddings_are_deterministic():
    from kitline.embeddings import HashingEmbedder

    left = HashingEmbedder()
    right = HashingEmbedder()
    texts = [product.index_text() for product in PRODUCTS]
    left.fit(texts)
    right.fit(texts)
    assert left.embed_one(texts[0]) == right.embed_one(texts[0])
    norm = sum(value * value for value in left.embed_one("usb4 dock"))
    assert norm == pytest.approx(1.0)
