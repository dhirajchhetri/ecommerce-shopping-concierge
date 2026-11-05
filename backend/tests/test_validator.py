from datetime import date

from kitline.schemas import BundleLineIn, BundleProposal
from kitline.validator import validate_bundle

TODAY = date(2026, 11, 5)


def _proposal(*lines: tuple[str, str, int], offer: str | None = None) -> BundleProposal:
    return BundleProposal(
        title="Test package",
        summary="A package under test.",
        rationale="Built in a test.",
        lines=[BundleLineIn(sku=sku, role=role, quantity=qty) for sku, role, qty in lines],
        financing_offer_id=offer,
    )


def test_valid_bundle_is_priced_from_the_catalog(catalog):
    outcome = validate_bundle(
        _proposal(("PW-SLIM-14", "primary", 1), ("PW-MOUSE", "accessory", 2), ("PW-CARE-1Y", "warranty", 1)),
        catalog,
        budget_cents=120_000,
        today=TODAY,
    )
    assert outcome.ok
    package = outcome.package
    assert package is not None
    mouse = next(line for line in package.lines if line.sku == "PW-MOUSE")
    assert mouse.unit_price_cents == 3_900
    assert mouse.line_total_cents == 7_800
    assert package.grand_total_cents == 99_900 + 7_800 + 7_900
    assert all(check.ok for check in package.checks)


def test_price_is_read_when_the_bundle_is_checked(catalog):
    catalog.get("PW-SLIM-14").price_cents = 40_000
    outcome = validate_bundle(
        _proposal(("PW-SLIM-14", "primary", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert outcome.ok
    assert outcome.package.lines[0].unit_price_cents == 40_000
    assert outcome.package.grand_total_cents == 40_000


def test_incompatible_accessory_is_rejected(catalog):
    outcome = validate_bundle(
        _proposal(("NS-AIR-14", "primary", 1), ("NS-DOCK-TB", "accessory", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert not outcome.ok
    assert outcome.package is None
    assert any("NS-DOCK-TB" in error for error in outcome.errors)


def test_stock_quantity_and_unknown_sku_are_rejected(catalog):
    oversell = validate_bundle(
        _proposal(("NS-REFURB-14", "primary", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert not oversell.ok
    assert any("stock" in error for error in oversell.errors)

    unknown = validate_bundle(
        _proposal(("NOT-A-SKU", "primary", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert any("Unknown SKU" in error for error in unknown.errors)


def test_budget_warranty_vendor_and_expired_offer_are_rejected(catalog):
    over = validate_bundle(
        _proposal(("PW-VECTOR-17", "primary", 1)),
        catalog,
        budget_cents=100_000,
        today=TODAY,
    )
    assert any("budget" in error for error in over.errors)

    wrong_vendor = validate_bundle(
        _proposal(("HB-STUDIO-16", "primary", 1), ("NS-CARE-2Y", "warranty", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert any("does not cover" in error for error in wrong_vendor.errors)

    inactive = validate_bundle(
        _proposal(("NS-PRO-16", "primary", 1), ("NS-CARE-OLD", "warranty", 1)),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert any("not an active plan" in error for error in inactive.errors)

    expired = validate_bundle(
        _proposal(("PW-SLIM-14", "primary", 1), offer="FLEX-OLD"),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert any("expired" in error for error in expired.errors)

    closed = validate_bundle(
        _proposal(("PW-SLIM-14", "primary", 1), offer="FLEX-CLOSED"),
        catalog,
        budget_cents=None,
        today=TODAY,
    )
    assert any("not active" in error for error in closed.errors)
