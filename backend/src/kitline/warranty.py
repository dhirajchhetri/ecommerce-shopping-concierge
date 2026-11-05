"""Vendor warranty plans. Synthetic terms and prices."""

from dataclasses import dataclass

from kitline.catalog_data import Product


@dataclass(frozen=True)
class WarrantyPlan:
    plan_id: str
    vendor: str
    name: str
    term_months: int
    price_cents: int
    categories: frozenset[str]
    active: bool


PLANS: tuple[WarrantyPlan, ...] = (
    WarrantyPlan("NS-CARE-2Y", "Northstar", "Northstar Care 2 Year", 24, 14_900, frozenset({"laptop"}), True),
    WarrantyPlan("NS-CARE-3Y", "Northstar", "Northstar Care 3 Year", 36, 21_900, frozenset({"laptop"}), True),
    WarrantyPlan("PW-CARE-1Y", "Pixelwell", "Pixelwell Care 1 Year", 12, 7_900, frozenset({"laptop"}), True),
    WarrantyPlan("HB-CARE-2Y", "Harbor", "Harbor Care 2 Year", 24, 12_900, frozenset({"laptop"}), True),
    WarrantyPlan("NS-MON-CARE", "Northstar", "Northstar Monitor Care", 24, 4_900, frozenset({"monitor"}), True),
    WarrantyPlan("NS-CARE-OLD", "Northstar", "Northstar legacy plan", 12, 1_000, frozenset({"laptop"}), False),
)

_BY_ID = {plan.plan_id: plan for plan in PLANS}


def get_plan(plan_id: str) -> WarrantyPlan | None:
    return _BY_ID.get(plan_id)


def plans_for(product: Product, *, active_only: bool = False) -> list[WarrantyPlan]:
    found = [
        plan
        for plan in PLANS
        if plan.vendor == product.vendor and product.category in plan.categories and (plan.active or not active_only)
    ]
    return sorted(found, key=lambda plan: (plan.price_cents, plan.plan_id))


def plan_covers(plan: WarrantyPlan, product: Product) -> tuple[bool, str]:
    if not plan.active:
        return False, f"{plan.plan_id} is not an active plan."
    if plan.vendor != product.vendor:
        return False, f"{plan.plan_id} is a {plan.vendor} plan and does not cover {product.vendor}."
    if product.category not in plan.categories:
        return False, f"{plan.plan_id} does not cover a {product.category}."
    return True, f"{plan.name} covers {product.name}."


def plan_dict(plan: WarrantyPlan) -> dict:
    return {
        "plan_id": plan.plan_id,
        "vendor": plan.vendor,
        "name": plan.name,
        "term_months": plan.term_months,
        "price_cents": plan.price_cents,
        "categories": sorted(plan.categories),
        "active": plan.active,
    }
