from datetime import date

from kitline.compatibility import check_products
from kitline.financing import best_eligible, eligibility, get_offer, monthly_payment_cents
from kitline.warranty import get_plan, plan_covers, plans_for


def test_usb4_dock_fits_pro_and_not_the_air(catalog):
    pro = catalog.get("NS-PRO-16")
    air = catalog.get("NS-AIR-14")
    dock = catalog.get("NS-DOCK-TB")
    usb_c = catalog.get("PW-DOCK-C")
    old = catalog.get("HB-DOCK-A")
    assert check_products(pro, dock)[0] is True
    assert check_products(air, dock)[0] is False
    assert check_products(air, usb_c)[0] is True
    assert check_products(pro, old)[0] is False
    mouse = catalog.get("PW-MOUSE")
    assert check_products(air, mouse)[0] is True


def test_warranty_plans_follow_the_vendor(catalog):
    northstar = plans_for(catalog.get("NS-PRO-16"))
    ids = {plan.plan_id for plan in northstar}
    assert "NS-CARE-2Y" in ids
    assert "PW-CARE-1Y" not in ids
    assert "NS-MON-CARE" not in ids
    inactive = get_plan("NS-CARE-OLD")
    assert plan_covers(inactive, catalog.get("NS-PRO-16"))[0] is False
    assert plan_covers(get_plan("NS-CARE-2Y"), catalog.get("NS-PRO-16"))[0] is True
    assert plan_covers(get_plan("NS-CARE-2Y"), catalog.get("HB-STUDIO-16"))[0] is False


def test_financing_flags_expired_and_closed_offers():
    today = date(2026, 11, 5)
    old = get_offer("FLEX-OLD")
    closed = get_offer("FLEX-CLOSED")
    assert eligibility(old, 100_000, today)[0] is False
    assert "expired" in eligibility(old, 100_000, today)[1]
    assert eligibility(closed, 100_000, today)[0] is False
    current = get_offer("LUMEN-12")
    assert eligibility(current, 100_000, today)[0] is True
    assert eligibility(current, 10_000, today)[0] is False
    best = best_eligible(180_000, today)
    assert best is not None
    assert best.offer_id == "LUMEN-12"


def test_zero_percent_payment_is_an_even_split():
    assert monthly_payment_cents(120_000, "0", 12) == 10_000


def test_interest_payment_uses_standard_amortization():
    from decimal import Decimal, ROUND_HALF_UP

    principal = 100_000
    apr = Decimal("9.9")
    months = 12
    rate = apr / Decimal(100) / Decimal(12)
    power = (1 + rate) ** months
    expected = (Decimal(principal) * rate * power / (power - 1)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    assert monthly_payment_cents(principal, "9.9", months) == int(expected)
    assert monthly_payment_cents(principal, "9.9", months) > principal // months
