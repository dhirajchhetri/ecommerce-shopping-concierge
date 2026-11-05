"""Deterministic package checks.

The model chooses SKUs. This module re-reads price, stock, compatibility,
warranty coverage, the budget, and the financing offer before anything is shown.
A package that fails is not returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kitline.catalog import Catalog
from kitline.compatibility import check_products
from kitline.financing import eligibility, get_offer, monthly_payment_cents
from kitline.schemas import BundleProposal, CheckOut, FinancingOut, LineOut, PackageOut
from kitline.warranty import get_plan, plan_covers


@dataclass
class ValidationOutcome:
    ok: bool
    errors: list[str]
    package: PackageOut | None


def _failed(errors: list[str], checks: list[CheckOut]) -> ValidationOutcome:
    return ValidationOutcome(ok=False, errors=errors, package=None)


def validate_bundle(
    proposal: BundleProposal,
    catalog: Catalog,
    *,
    budget_cents: int | None,
    today: date,
) -> ValidationOutcome:
    errors: list[str] = []
    checks: list[CheckOut] = []

    primaries = [line for line in proposal.lines if line.role == "primary"]
    if len(primaries) != 1:
        errors.append("A package needs exactly one primary item.")
        checks.append(CheckOut(name="single_primary", ok=False, detail="A package needs exactly one primary item."))
    else:
        checks.append(CheckOut(name="single_primary", ok=True, detail=f"Primary item is {primaries[0].sku}."))

    skus = [line.sku for line in proposal.lines]
    known = True
    if len(skus) != len(set(skus)):
        known = False
        errors.append("The package repeats a SKU.")
    for line in proposal.lines:
        if line.role == "warranty":
            if get_plan(line.sku) is None:
                known = False
                errors.append(f"Unknown warranty plan {line.sku}.")
        elif catalog.get(line.sku) is None:
            known = False
            errors.append(f"Unknown SKU {line.sku}.")
    checks.append(
        CheckOut(
            name="items_known",
            ok=known and len(skus) == len(set(skus)),
            detail="Every SKU is in the catalog." if known and len(skus) == len(set(skus)) else "A SKU or warranty plan is unknown.",
        )
    )

    primary_product = catalog.get(primaries[0].sku) if len(primaries) == 1 else None

    stock_ok = True
    for line in proposal.lines:
        if line.role == "warranty":
            if line.quantity != 1:
                stock_ok = False
                errors.append(f"Warranty {line.sku} must have quantity 1.")
            continue
        product = catalog.get(line.sku)
        if product is None:
            continue
        if line.quantity > product.stock:
            stock_ok = False
            errors.append(f"{line.sku} has {product.stock} in stock, which is below quantity {line.quantity}.")
    checks.append(
        CheckOut(
            name="stock",
            ok=stock_ok,
            detail="Every item is in stock." if stock_ok else "A line asks for more units than are in stock.",
        )
    )

    compat_ok = True
    if primary_product is None:
        if any(line.role == "accessory" for line in proposal.lines):
            compat_ok = False
            errors.append("Accessories need a known primary item before compatibility can be checked.")
    else:
        for line in proposal.lines:
            if line.role != "accessory":
                continue
            accessory = catalog.get(line.sku)
            if accessory is None:
                continue
            ok, reason = check_products(primary_product, accessory)
            if not ok:
                compat_ok = False
                errors.append(f"{line.sku} is not compatible with {primary_product.sku}: {reason}")
    checks.append(
        CheckOut(
            name="compatibility",
            ok=compat_ok,
            detail="Accessories match the primary item." if compat_ok else "An accessory is not compatible with the primary item.",
        )
    )

    warranty_lines = [line for line in proposal.lines if line.role == "warranty"]
    warranty_ok = True
    if len(warranty_lines) > 1:
        warranty_ok = False
        errors.append("A package can include only one warranty.")
    elif warranty_lines and primary_product is None:
        warranty_ok = False
        errors.append("A warranty needs a known primary item.")
    elif warranty_lines and primary_product is not None:
        plan = get_plan(warranty_lines[0].sku)
        if plan is not None:
            ok, reason = plan_covers(plan, primary_product)
            if not ok:
                warranty_ok = False
                errors.append(reason)
    checks.append(
        CheckOut(
            name="warranty",
            ok=warranty_ok,
            detail="Warranty covers the primary item." if warranty_ok else "Warranty does not cover the primary item.",
        )
    )

    if errors:
        checks.append(CheckOut(name="budget", ok=False, detail="Not priced because an earlier check failed."))
        checks.append(CheckOut(name="financing", ok=False, detail="Not priced because an earlier check failed."))
        checks.append(CheckOut(name="totals", ok=False, detail="Not priced because an earlier check failed."))
        return _failed(errors, checks)

    lines: list[LineOut] = []
    for line in proposal.lines:
        if line.role == "warranty":
            plan = get_plan(line.sku)
            assert plan is not None
            lines.append(
                LineOut(
                    sku=plan.plan_id,
                    name=plan.name,
                    vendor=plan.vendor,
                    category="warranty",
                    role="warranty",
                    quantity=1,
                    unit_price_cents=plan.price_cents,
                    line_total_cents=plan.price_cents,
                )
            )
            continue
        product = catalog.get(line.sku)
        assert product is not None
        lines.append(
            LineOut(
                sku=product.sku,
                name=product.name,
                vendor=product.vendor,
                category=product.category,
                role=line.role,
                quantity=line.quantity,
                unit_price_cents=product.price_cents,
                line_total_cents=product.price_cents * line.quantity,
            )
        )

    grand_total = sum(line.line_total_cents for line in lines)
    budget_ok = budget_cents is None or grand_total <= budget_cents
    if not budget_ok:
        assert budget_cents is not None
        errors.append(f"Package total {grand_total} cents is over the budget of {budget_cents} cents.")
    if budget_cents is None:
        budget_detail = "No budget was set."
    elif budget_ok:
        budget_detail = f"Total {grand_total} cents is within {budget_cents} cents."
    else:
        budget_detail = f"Total {grand_total} cents is over {budget_cents} cents."
    checks.append(CheckOut(name="budget", ok=budget_ok, detail=budget_detail))

    financing = None
    financing_ok = True
    if proposal.financing_offer_id:
        offer = get_offer(proposal.financing_offer_id)
        if offer is None:
            financing_ok = False
            errors.append(f"Unknown financing offer {proposal.financing_offer_id}.")
        else:
            ok, reason = eligibility(offer, grand_total, today)
            if not ok:
                financing_ok = False
                errors.append(reason)
            else:
                financing = FinancingOut(
                    offer_id=offer.offer_id,
                    provider=offer.provider,
                    apr_percent=offer.apr_percent,
                    term_months=offer.term_months,
                    monthly_payment_cents=monthly_payment_cents(grand_total, offer.apr_percent, offer.term_months),
                )
        detail = "Financing offer is open for this total." if financing_ok else "Financing offer was rejected."
    else:
        detail = "No financing selected."
    checks.append(CheckOut(name="financing", ok=financing_ok, detail=detail))
    checks.append(
        CheckOut(
            name="totals",
            ok=not errors,
            detail=f"Grand total is {grand_total} cents, priced from the catalog.",
        )
    )

    if errors:
        return _failed(errors, checks)

    package = PackageOut(
        title=proposal.title,
        summary=proposal.summary,
        rationale=proposal.rationale,
        lines=lines,
        grand_total_cents=grand_total,
        financing=financing,
        checks=checks,
    )
    return ValidationOutcome(ok=True, errors=[], package=package)
