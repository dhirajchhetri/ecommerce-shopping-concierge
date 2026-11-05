from datetime import date

import pytest

from kitline.catalog import Catalog
from kitline.service import ConciergeService
from kitline.sessions import MemorySessionStore
from kitline.stub_model import StubModel


@pytest.fixture
def today() -> date:
    return date(2026, 11, 5)


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.create_default()


@pytest.fixture
def service(catalog: Catalog, today: date) -> ConciergeService:
    return ConciergeService(
        catalog,
        MemorySessionStore(),
        StubModel(),
        clock=lambda: today,
    )
