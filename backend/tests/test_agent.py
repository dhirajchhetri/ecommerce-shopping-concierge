from datetime import date

import pytest

from kitline.selection import parse_budget_phrase, parse_intent
from kitline.service import ConciergeService
from kitline.sessions import MemorySessionStore
from kitline.stub_model import StubModel


def test_budget_phrases():
    assert parse_budget_phrase("Budget $2,500 for a laptop") == 250_000
    assert parse_budget_phrase("under $1,200") == 120_000
    assert parse_budget_phrase("budget of 800 dollars") == 80_000
    assert parse_budget_phrase("no number here") is None


def test_video_editing_package_stays_inside_the_budget(service):
    session = service.create_session()
    result = service.converse(
        session.session_id,
        "I need a laptop for video editing, a monitor, and a two-year warranty. Budget $2,500.",
        budget_cents=None,
    )
    assert result.status == "validated"
    assert result.source == "agent"
    assert result.attempts == 1
    package = result.package
    assert package is not None
    assert package.grand_total_cents <= 250_000
    categories = {line.category for line in package.lines}
    assert "laptop" in categories
    assert "monitor" in categories
    assert "warranty" in categories
    laptop = next(line for line in package.lines if line.category == "laptop")
    warranty = next(line for line in package.lines if line.role == "warranty")
    assert laptop.sku in {"NS-PRO-16", "HB-STUDIO-16"}
    assert warranty.vendor == laptop.vendor
    assert warranty.unit_price_cents > 0
    assert "search_catalog" in result.tools_used
    assert "check_compatibility" in result.tools_used
    assert "lookup_warranties" in result.tools_used
    assert "get_financing_offers" in result.tools_used
    assert all(check.ok for check in package.checks)
    assert package.financing is None


def test_student_setup_picks_the_laptop_that_fits(service):
    session = service.create_session()
    result = service.converse(
        session.session_id,
        "Student setup: a light laptop, a mouse, and headphones under $1,200.",
        budget_cents=120_000,
    )
    package = result.package
    assert result.status == "validated"
    assert package is not None
    assert package.grand_total_cents <= 120_000
    assert {line.category for line in package.lines} >= {"laptop", "mouse", "headset"}
    assert next(line for line in package.lines if line.role == "primary").sku == "PW-SLIM-14"


def test_creator_dock_is_compatible_and_financed(service):
    session = service.create_session()
    result = service.converse(
        session.session_id,
        "Creator laptop with a USB4 dock and financing.",
        budget_cents=250_000,
    )
    package = result.package
    assert result.status == "validated"
    assert package is not None
    primary = next(line for line in package.lines if line.role == "primary")
    dock = next(line for line in package.lines if line.category == "dock")
    assert primary.sku in {"NS-PRO-16", "HB-STUDIO-16", "PW-VECTOR-17"}
    assert dock.sku != "HB-DOCK-A"
    assert package.financing is not None
    assert package.financing.offer_id == "LUMEN-12"
    assert package.financing.monthly_payment_cents > 0


def test_follow_up_drops_the_monitor_and_gets_cheaper(service):
    session = service.create_session()
    first = service.converse(
        session.session_id,
        "I need a laptop for video editing, a monitor, and a two-year warranty.",
        budget_cents=250_000,
    )
    second = service.converse(
        session.session_id,
        "Make it cheaper and drop the monitor.",
        budget_cents=250_000,
    )
    assert first.package is not None and second.package is not None
    assert second.package.grand_total_cents < first.package.grand_total_cents
    assert all(line.category != "monitor" for line in second.package.lines)
    stored = service.get_session(session.session_id)
    assert [turn.role for turn in stored.turns] == ["user", "assistant", "user", "assistant"]


def test_bad_sku_is_retried_then_accepted(catalog, today):
    service = ConciergeService(
        catalog,
        MemorySessionStore(),
        StubModel(fault="bad-sku-once"),
        clock=lambda: today,
    )
    session = service.create_session()
    result = service.converse(session.session_id, "A light student laptop under $1,200.", budget_cents=120_000)
    assert result.status == "validated"
    assert result.source == "agent"
    assert result.attempts == 2
    assert result.package is not None
    assert result.package.lines[0].sku == "PW-SLIM-14"


def test_repeated_invalid_drafts_fall_back(catalog, today):
    service = ConciergeService(
        catalog,
        MemorySessionStore(),
        StubModel(fault="always-bad"),
        clock=lambda: today,
    )
    session = service.create_session()
    result = service.converse(
        session.session_id,
        "I need a laptop for video editing and a monitor. Budget $2,500.",
        budget_cents=None,
    )
    assert result.source == "fallback"
    assert result.attempts == 2
    assert result.status == "validated"
    assert result.package is not None
    assert result.package.grand_total_cents <= 250_000
    assert all(check.ok for check in result.package.checks)


def test_incompatible_draft_is_corrected(catalog, today):
    service = ConciergeService(
        catalog,
        MemorySessionStore(),
        StubModel(fault="incompatible-once"),
        clock=lambda: today,
    )
    session = service.create_session()
    result = service.converse(session.session_id, "A student laptop and a mouse under $1,200.", budget_cents=None)
    assert result.attempts == 2
    assert result.package is not None
    assert all(line.sku != "HB-DOCK-A" for line in result.package.lines)


def test_tiny_budget_is_unfulfilled(service):
    session = service.create_session()
    result = service.converse(session.session_id, "A laptop for class.", budget_cents=1_000)
    assert result.status == "unfulfilled"
    assert result.package is None
    assert result.source == "fallback"


@pytest.mark.parametrize(
    ("message", "budget"),
    [
        ("I need a laptop for video editing, a monitor, and a two-year warranty. Budget $2,500.", None),
        ("Student setup: a light laptop, a mouse, and headphones under $1,200.", 120_000),
        ("Creator laptop with a USB4 dock and financing.", 250_000),
    ],
)
def test_golden_requests_pass_the_checks(service, message, budget):
    session = service.create_session()
    result = service.converse(session.session_id, message, budget_cents=budget)
    assert result.status == "validated"
    assert result.package is not None
    assert all(check.ok for check in result.package.checks)
    if budget is not None:
        assert result.package.grand_total_cents <= budget
