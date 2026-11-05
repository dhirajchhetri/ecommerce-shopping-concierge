"""Tools the concierge can call. Each one returns JSON the model can read."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from strands import tool

from kitline.catalog import Catalog
from kitline.compatibility import check_products
from kitline.financing import OFFERS, offer_dict
from kitline.warranty import plan_dict, plans_for

SYSTEM_PROMPT = """You are Kitline, a shopping concierge for a small electronics catalog.
Assemble one package: a single primary product, optional accessories, at most one warranty, and an optional financing offer.

Rules:
- Use only SKUs and warranty plan ids that tools return. Never invent an identifier.
- Do not invent prices. The server prices every line from the catalog after you finish.
- Call search_catalog before choosing products. Search again with a category when the first results miss one.
- Call check_compatibility for every accessory against the one primary item. Drop any accessory the tool rejects.
- Call lookup_warranties for the primary item. Add a plan only when the shopper asked for a warranty, the plan is active, and it fits the budget.
- Call get_financing_offers with the package total in cents. Set financing_offer_id only when the shopper asked about financing and the offer is eligible. Otherwise leave it null.
- When the prompt contains BUDGET_CENTS, the package total must be less than or equal to that number. The value is cents, not dollars.
- Use exactly one line with role "primary".
- When the prompt contains VALIDATION_FAILED, read every error and submit a corrected package.
- Finish by calling BundleProposal. Do not describe an unchecked alternative.
"""


def build_tools(catalog: Catalog, clock: Callable[[], date]) -> list:
    @tool
    def search_catalog(query: str, category: str = "", limit: int = 6) -> dict:
        """Search the product catalog by meaning. category is optional: laptop, monitor, dock, keyboard, mouse, or headset."""
        bounded = max(1, min(limit, 8))
        hits = catalog.search(query, category=category or None, limit=bounded)
        return {
            "tool": "search_catalog",
            "query": query,
            "echo_category": category,
            "hits": [hit.as_dict() for hit in hits],
        }

    @tool
    def check_compatibility(primary_sku: str, accessory_sku: str) -> dict:
        """Check whether an accessory works with the primary product."""
        primary = catalog.get(primary_sku)
        accessory = catalog.get(accessory_sku)
        if primary is None or accessory is None:
            missing = primary_sku if primary is None else accessory_sku
            return {
                "tool": "check_compatibility",
                "primary_sku": primary_sku,
                "accessory_sku": accessory_sku,
                "compatible": False,
                "reason": f"Unknown SKU {missing}.",
            }
        compatible, reason = check_products(primary, accessory)
        return {
            "tool": "check_compatibility",
            "primary_sku": primary_sku,
            "accessory_sku": accessory_sku,
            "compatible": compatible,
            "reason": reason,
        }

    @tool
    def lookup_warranties(sku: str) -> dict:
        """List warranty plans for a product, including inactive plans and an active flag."""
        product = catalog.get(sku)
        if product is None:
            return {"tool": "lookup_warranties", "sku": sku, "plans": [], "reason": f"Unknown SKU {sku}."}
        plans = [plan_dict(plan) for plan in plans_for(product)]
        return {"tool": "lookup_warranties", "sku": sku, "plans": plans}

    @tool
    def get_financing_offers(amount_cents: int) -> dict:
        """List financing offers for a total in cents. eligible is computed here and checked again later."""
        today = clock()
        return {
            "tool": "get_financing_offers",
            "amount_cents": amount_cents,
            "offers": [offer_dict(offer, amount_cents, today) for offer in OFFERS],
        }

    return [search_catalog, check_compatibility, lookup_warranties, get_financing_offers]
