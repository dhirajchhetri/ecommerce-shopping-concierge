"""Request and response models.

BundleProposal is the schema the agent must fill. Prices are not fields on it:
the validator reads them from the catalog when the package is checked.
"""

from typing import Literal

from pydantic import BaseModel, Field


class BundleLineIn(BaseModel):
    sku: str = Field(description="SKU or warranty plan id returned by a tool")
    quantity: int = Field(default=1, ge=1, le=5)
    role: Literal["primary", "accessory", "warranty"]


class BundleProposal(BaseModel):
    """Submit the one package the shopper should see. Call this last, after the other tools."""

    title: str = Field(description="Short package name")
    summary: str = Field(description="One or two sentences naming the items and why they fit")
    rationale: str = Field(
        description="Which lookups you ran: catalog search, compatibility, warranty, financing, and budget"
    )
    lines: list[BundleLineIn] = Field(min_length=1, max_length=8)
    financing_offer_id: str | None = Field(
        default=None,
        description="Offer id returned by get_financing_offers, or null when the shopper did not ask to finance",
    )


class CheckOut(BaseModel):
    name: str
    ok: bool
    detail: str


class LineOut(BaseModel):
    sku: str
    name: str
    vendor: str
    category: str
    role: Literal["primary", "accessory", "warranty"]
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class FinancingOut(BaseModel):
    offer_id: str
    provider: str
    apr_percent: str
    term_months: int
    monthly_payment_cents: int


class PackageOut(BaseModel):
    title: str
    summary: str
    rationale: str
    lines: list[LineOut]
    grand_total_cents: int
    financing: FinancingOut | None
    checks: list[CheckOut]


class TurnOut(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    created_at: str
    package: PackageOut | None = None
    status: Literal["validated", "unfulfilled"] | None = None
    source: Literal["agent", "fallback"] | None = None
    attempts: int | None = None


class SessionOut(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    turns: list[TurnOut]


class ConverseResponse(BaseModel):
    session_id: str
    status: Literal["validated", "unfulfilled"]
    source: Literal["agent", "fallback"]
    attempts: int
    message: str
    package: PackageOut | None
    tools_used: list[str]
    turns: list[TurnOut]


class ProductOut(BaseModel):
    sku: str
    name: str
    vendor: str
    category: str
    price_cents: int
    stock: int
    description: str


class HealthOut(BaseModel):
    status: Literal["ok"]
    mode: str
    model: str
    vector_store: str
    session_store: str
    catalog_size: int


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    budget_cents: int | None = Field(default=None, ge=0, le=10_000_000)
