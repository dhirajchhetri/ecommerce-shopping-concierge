"""HTTP API for the shopper UI and for tests."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from kitline import __version__
from kitline.config import Settings, get_settings
from kitline.runtime import build_service
from kitline.schemas import ConverseResponse, HealthOut, MessageIn, ProductOut, SessionOut
from kitline.service import ConciergeService, SessionNotFound

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, service: ConciergeService | None = None) -> FastAPI:
    settings = settings or get_settings()
    service = service or build_service(settings)
    app = FastAPI(title="Kitline", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list() or ["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.service = service

    @app.get("/api/health", response_model=HealthOut)
    def health() -> HealthOut:
        model_name = "stub" if settings.mode == "offline" else settings.bedrock_model_id
        return HealthOut(
            status="ok",
            mode=settings.mode,
            model=model_name,
            vector_store=settings.vector_store,
            session_store=settings.session_store,
            catalog_size=len(service.catalog.products),
        )

    @app.get("/api/catalog", response_model=list[ProductOut])
    def catalog() -> list[ProductOut]:
        return [
            ProductOut(
                sku=product.sku,
                name=product.name,
                vendor=product.vendor,
                category=product.category,
                price_cents=product.price_cents,
                stock=product.stock,
                description=product.description,
            )
            for product in service.catalog.all_products()
        ]

    @app.post("/api/sessions", response_model=SessionOut)
    def create_session() -> SessionOut:
        return service.create_session()

    @app.get("/api/sessions/{session_id}", response_model=SessionOut)
    def read_session(session_id: str) -> SessionOut:
        try:
            return service.get_session(session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="Unknown session.") from None

    @app.post("/api/sessions/{session_id}/messages", response_model=ConverseResponse)
    def post_message(session_id: str, body: MessageIn) -> ConverseResponse:
        try:
            return service.converse(session_id, body.message, body.budget_cents)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="Unknown session.") from None

    return app


app = create_app()
