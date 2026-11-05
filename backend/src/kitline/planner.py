"""Decide the next tool call for the offline model.

The decision reads only the shopper prompt and tool results already in the
conversation. It does not look at the catalog by itself. That keeps the stub
on the same tool path a hosted model uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kitline.financing import offer_rank
from kitline.schemas import BundleLineIn, BundleProposal
from kitline.selection import choose_primary, dedupe_hits, inherit_categories, parse_intent, pick_warranty


@dataclass
class ToolCall:
    name: str
    arguments: dict


def previous_categories(prompt: str) -> list[str]:
    for line in prompt.splitlines():
        if not line.startswith("PREVIOUS_PACKAGE:"):
            continue
        raw = line[len("PREVIOUS_PACKAGE:") :].strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        categories: list[str] = []
        for item in payload.get("lines", []):
            category = item.get("category")
            if item.get("role") == "warranty" or not category or category in categories:
                continue
            categories.append(category)
        return categories
    return []


def _hits(results: list[dict]) -> list[dict]:
    return dedupe_hits([result.get("hits", []) for result in results if result.get("tool") == "search_catalog"])


def _searched(results: list[dict], category: str) -> bool:
    return any(
        result.get("tool") == "search_catalog" and result.get("echo_category", "") == category for result in results
    )


def _has_stocked(hits: list[dict], category: str) -> bool:
    return any(hit["category"] == category and hit["stock"] > 0 for hit in hits)


def _compat_index(results: list[dict]) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for result in results:
        if result.get("tool") != "check_compatibility":
            continue
        index[(result["primary_sku"], result["accessory_sku"])] = result
    return index


def _warranty_plans(results: list[dict]) -> list[dict] | None:
    for result in reversed(results):
        if result.get("tool") == "lookup_warranties":
            return list(result.get("plans", []))
    return None


def _offer_payload(results: list[dict]) -> list[dict] | None:
    for result in reversed(results):
        if result.get("tool") == "get_financing_offers":
            return list(result.get("offers", []))
    return None


def _search(query: str, category: str) -> ToolCall:
    return ToolCall("search_catalog", {"query": query, "category": category, "limit": 8 if category == "" else 6})


def _shrink(
    primary: dict, accessories: list[dict], warranty: dict | None, budget: int | None
) -> tuple[list[dict], dict | None, int]:
    chosen = list(accessories)
    plan = warranty

    def total() -> int:
        extra = plan["price_cents"] if plan else 0
        return primary["price_cents"] + sum(item["price_cents"] for item in chosen) + extra

    if budget is None:
        return chosen, plan, total()
    while chosen and total() > budget:
        drop = max(chosen, key=lambda item: (item["price_cents"], item["sku"]))
        chosen.remove(drop)
    if plan is not None and total() > budget:
        plan = None
    return chosen, plan, total()


def _proposal(
    primary: dict,
    accessories: list[dict],
    warranty: dict | None,
    offer_id: str | None,
    force_bad: str | None,
) -> ToolCall:
    lines = [BundleLineIn(sku=primary["sku"], quantity=1, role="primary")]
    lines.extend(BundleLineIn(sku=item["sku"], quantity=1, role="accessory") for item in accessories)
    names = [primary["name"]] + [item["name"] for item in accessories]
    if warranty is not None:
        lines.append(BundleLineIn(sku=warranty["plan_id"], quantity=1, role="warranty"))
        names.append(warranty["name"])
    if force_bad == "bad-sku":
        lines = [BundleLineIn(sku="NOT-A-SKU", quantity=1, role="primary")]
        names = ["unknown item"]
        offer_id = None
    elif force_bad == "incompatible":
        lines.append(BundleLineIn(sku="HB-DOCK-A", quantity=1, role="accessory"))
        names.append("Harbor USB-A Mini Dock")
    proposal = BundleProposal(
        title=f"{primary['name']} package",
        summary="Includes " + ", ".join(names) + ".",
        rationale=(
            "Searched the catalog, checked accessory compatibility, looked up warranty plans, "
            "and reviewed financing offers. The server prices the package and repeats those checks."
        ),
        lines=lines,
        financing_offer_id=offer_id,
    )
    return ToolCall("BundleProposal", proposal.model_dump())


def plan_next(prompt: str, results: list[dict], *, force_bad: str | None) -> ToolCall:
    intent = parse_intent(prompt)
    earlier = previous_categories(prompt)
    if earlier:
        intent = inherit_categories(intent, earlier)
    query = intent.shopper_text or intent.primary_category
    hits = _hits(results)

    if not _searched(results, ""):
        return _search(query, "")
    if intent.primary_category and not _has_stocked(hits, intent.primary_category) and not _searched(
        results, intent.primary_category
    ):
        return _search(query, intent.primary_category)
    for category in intent.accessory_categories:
        if not _has_stocked(hits, category) and not _searched(results, category):
            return _search(category, category)

    # Refresh after the searches above have been recorded on later turns.
    hits = _hits(results)
    primary = choose_primary(hits, intent)
    if primary is None:
        stocked = [hit for hit in hits if hit["category"] == intent.primary_category and hit["stock"] > 0]
        if not stocked:
            stocked = [hit for hit in hits if hit["stock"] > 0]
        stocked.sort(key=lambda hit: (hit["price_cents"], hit["sku"]))
        if not stocked:
            return _proposal(
                {"sku": "NOT-A-SKU", "name": "No match", "price_cents": 0},
                [],
                None,
                None,
                "bad-sku",
            )
        primary = stocked[0]

    compat = _compat_index(results)
    chosen: list[dict] = []
    spent = primary["price_cents"]
    for category in intent.accessory_categories:
        candidates = [hit for hit in hits if hit["category"] == category and hit["stock"] > 0]
        if intent.prefer_cheap:
            candidates.sort(key=lambda hit: (hit["price_cents"], hit["sku"]))
        else:
            candidates.sort(key=lambda hit: (-hit.get("score", 0.0), hit["price_cents"], hit["sku"]))
        for candidate in candidates:
            record = compat.get((primary["sku"], candidate["sku"]))
            if record is None:
                if len(results) >= 12:
                    break
                return ToolCall(
                    "check_compatibility",
                    {"primary_sku": primary["sku"], "accessory_sku": candidate["sku"]},
                )
            if not record.get("compatible"):
                continue
            if intent.budget_cents is not None and spent + candidate["price_cents"] > intent.budget_cents:
                continue
            chosen.append(candidate)
            spent += candidate["price_cents"]
            break

    plans = _warranty_plans(results)
    if plans is None:
        return ToolCall("lookup_warranties", {"sku": primary["sku"]})
    warranty = None
    if intent.wants_warranty:
        remaining = None if intent.budget_cents is None else intent.budget_cents - spent
        warranty = pick_warranty(plans, intent.warranty_term_months, remaining)

    chosen, warranty, total = _shrink(primary, chosen, warranty, intent.budget_cents)
    offers = _offer_payload(results)
    if offers is None:
        return ToolCall("get_financing_offers", {"amount_cents": max(total, 0)})

    offer_id = None
    if intent.wants_financing:
        eligible = [offer for offer in offers if offer.get("eligible")]
        eligible.sort(
            key=lambda offer: offer_rank(
                str(offer["apr_percent"]),
                int(offer["term_months"]),
                int(offer.get("monthly_payment_cents") or 0),
                offer["offer_id"],
            )
        )
        if eligible:
            offer_id = eligible[0]["offer_id"]

    return _proposal(primary, chosen, warranty, offer_id, force_bad)


def parse_tool_results(messages: list[dict]) -> list[dict]:
    found: list[dict] = []
    for message in messages:
        for block in message.get("content", []):
            tool_result = block.get("toolResult")
            if not tool_result:
                continue
            for content in tool_result.get("content", []):
                raw = content.get("text")
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    found.append(payload)
    return found


def force_flag(fault: str, prompt: str) -> str | None:
    if fault == "always-bad":
        return "bad-sku"
    if "VALIDATION_FAILED" in prompt:
        return None
    if fault == "bad-sku-once":
        return "bad-sku"
    if fault == "incompatible-once":
        return "incompatible"
    return None


def latest_user_text(messages: list[dict]) -> str:
    text = ""
    for message in messages:
        if message.get("role") != "user":
            continue
        for block in message.get("content", []):
            if "text" in block:
                text = block["text"]
    return text
