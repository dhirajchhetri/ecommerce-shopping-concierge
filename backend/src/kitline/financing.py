"""Mock financing partners.

LumenPay, Harbor Credit, and Northstar Flex are fictional. Offers include an
expired promotion and a closed plan so the validator can reject them. The
monthly payment is computed here; the model only chooses an offer id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class FinancingOffer:
    offer_id: str
    provider: str
    apr_percent: str
    term_months: int
    min_amount_cents: int
    max_amount_cents: int
    active: bool
    expires_on: date


OFFERS: tuple[FinancingOffer, ...] = (
    FinancingOffer("LUMEN-12", "LumenPay", "0", 12, 50_000, 400_000, True, date(2030, 12, 31)),
    FinancingOffer("LUMEN-24", "LumenPay", "9.9", 24, 80_000, 500_000, True, date(2030, 12, 31)),
    FinancingOffer("HARBOR-6", "Harbor Credit", "0", 6, 20_000, 250_000, True, date(2030, 12, 31)),
    FinancingOffer("FLEX-OLD", "Northstar Flex", "0", 18, 0, 900_000, True, date(2020, 1, 1)),
    FinancingOffer("FLEX-CLOSED", "Northstar Flex", "4.9", 12, 0, 900_000, False, date(2030, 12, 31)),
)

_BY_ID = {offer.offer_id: offer for offer in OFFERS}


def get_offer(offer_id: str) -> FinancingOffer | None:
    return _BY_ID.get(offer_id)


def monthly_payment_cents(principal_cents: int, apr_percent: str, term_months: int) -> int:
    """Standard amortization, rounded half up to the nearest cent.

    A 0% plan is principal divided by the term. The last installment in a real
    loan can differ by a few cents; this returns the regular installment only.
    """
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    if principal_cents < 0:
        raise ValueError("principal_cents cannot be negative")
    principal = Decimal(principal_cents)
    months = Decimal(term_months)
    apr = Decimal(apr_percent)
    if apr == 0:
        return int((principal / months).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    monthly_rate = apr / Decimal(100) / Decimal(12)
    power = (1 + monthly_rate) ** term_months
    payment = principal * monthly_rate * power / (power - 1)
    return int(payment.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def eligibility(offer: FinancingOffer, amount_cents: int, today: date) -> tuple[bool, str]:
    if not offer.active:
        return False, f"{offer.offer_id} is not active."
    if offer.expires_on < today:
        return False, f"{offer.offer_id} expired on {offer.expires_on.isoformat()}."
    if amount_cents < offer.min_amount_cents or amount_cents > offer.max_amount_cents:
        return (
            False,
            f"{offer.offer_id} covers {offer.min_amount_cents} to {offer.max_amount_cents} cents, "
            f"not {amount_cents}.",
        )
    return True, f"{offer.offer_id} is open for {amount_cents} cents."


def offer_dict(offer: FinancingOffer, amount_cents: int, today: date) -> dict:
    ok, reason = eligibility(offer, amount_cents, today)
    payment = monthly_payment_cents(amount_cents, offer.apr_percent, offer.term_months) if ok else None
    return {
        "offer_id": offer.offer_id,
        "provider": offer.provider,
        "apr_percent": offer.apr_percent,
        "term_months": offer.term_months,
        "min_amount_cents": offer.min_amount_cents,
        "max_amount_cents": offer.max_amount_cents,
        "active": offer.active,
        "expires_on": offer.expires_on.isoformat(),
        "eligible": ok,
        "reason": reason,
        "monthly_payment_cents": payment,
    }


def offer_rank(apr_percent: str, term_months: int, monthly_payment_cents_value: int, offer_id: str) -> tuple[int, int, str]:
    """Lower is better: a 0% plan beats interest, then a smaller installment, then id."""
    total_cost = 0 if Decimal(apr_percent) == 0 else monthly_payment_cents_value * term_months
    return (total_cost, monthly_payment_cents_value, offer_id)


def best_eligible(amount_cents: int, today: date) -> FinancingOffer | None:
    ranked: list[tuple[tuple[int, int, str], FinancingOffer]] = []
    for offer in OFFERS:
        ok, _reason = eligibility(offer, amount_cents, today)
        if not ok:
            continue
        payment = monthly_payment_cents(amount_cents, offer.apr_percent, offer.term_months)
        ranked.append((offer_rank(offer.apr_percent, offer.term_months, payment, offer.offer_id), offer))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]
