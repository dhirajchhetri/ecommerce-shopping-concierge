"""Shared parsing and a deterministic package builder.

The builder is the fallback used after both agent attempts are rejected. It reads
the catalog directly. The agent path is not allowed to skip its tools; see
planner.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from kitline.catalog import Catalog
from kitline.compatibility import check_products
from kitline.financing import best_eligible
from kitline.schemas import BundleLineIn, BundleProposal
from kitline.warranty import plan_dict, plans_for

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "laptop": ("laptop", "notebook"),
    "monitor": ("monitor", "display"),
    "dock": ("dock", "docking"),
    "keyboard": ("keyboard",),
    "mouse": ("mouse", "mice"),
    "headset": ("headset", "headphones", "headphone"),
}

_BUDGET_DOLLAR = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")
_BUDGET_WORD = re.compile(
    r"\b(?:under|below|budget of|budget)\s+\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?\b",
    re.IGNORECASE,
)
_BUDGET_UNIT = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d+)\s*(?:dollars|usd)\b", re.IGNORECASE)
_DROP = re.compile(r"\b(?:drop|remove|without)\b(?:\s+\w+){0,4}\s+\b([a-z]+)\b", re.IGNORECASE)
_CHEAP = re.compile(r"\b(?:cheaper|less expensive|lower price)\b", re.IGNORECASE)
_WARRANTY_TERM = (
    (re.compile(r"\b(?:two[\s-]?year|2[\s-]?year)\b", re.IGNORECASE), 24),
    (re.compile(r"\b(?:three[\s-]?year|3[\s-]?year)\b", re.IGNORECASE), 36),
    (re.compile(r"\b(?:one[\s-]?year|1[\s-]?year)\b", re.IGNORECASE), 12),
)


@dataclass
class Intent:
    shopper_text: str
    budget_cents: int | None
    primary_category: str
    accessory_categories: list[str]
    wants_warranty: bool
    warranty_term_months: int | None
    wants_financing: bool
    prefer_cheap: bool
    categories_explicit: bool = False
    dropped: set[str] = field(default_factory=set)


def shopper_text(prompt: str) -> str:
    if "SHOPPER_MESSAGE:" in prompt:
        body = prompt.split("SHOPPER_MESSAGE:", 1)[1]
        body = body.split("VALIDATION_FAILED", 1)[0]
        return body.strip()
    return prompt.strip()


def _dollars_to_cents(whole: str, fraction: str | None) -> int:
    dollars = int(whole.replace(",", ""))
    cents = int(fraction) if fraction else 0
    return dollars * 100 + cents


def parse_budget_phrase(text: str) -> int | None:
    """Read a budget written in dollars from shopper prose. Not for BUDGET_CENTS lines."""
    word = _BUDGET_WORD.search(text)
    if word:
        return _dollars_to_cents(word.group(1), word.group(2))
    unit = _BUDGET_UNIT.search(text)
    if unit:
        return _dollars_to_cents(unit.group(1), None)
    dollar = _BUDGET_DOLLAR.search(text)
    if dollar:
        return _dollars_to_cents(dollar.group(1), dollar.group(2))
    return None


def parse_budget_cents_line(prompt: str) -> int | None:
    match = re.search(r"BUDGET_CENTS:\s*(\d+)", prompt)
    if not match:
        return None
    return int(match.group(1))


def _mentioned(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for category, words in _KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
            found.append(category)
    return found


def _dropped(text: str) -> set[str]:
    dropped: set[str] = set()
    for match in _DROP.finditer(text.lower()):
        token = match.group(1)
        for category, words in _KEYWORDS.items():
            if token == category or token in words:
                dropped.add(category)
    return dropped


def parse_intent(prompt: str, *, budget_cents: int | None = None) -> Intent:
    text = shopper_text(prompt)
    mentioned = _mentioned(text)
    dropped = _dropped(text)
    categories = [category for category in mentioned if category not in dropped]
    explicit = bool(mentioned) or bool(dropped)
    term = None
    for pattern, months in _WARRANTY_TERM:
        if pattern.search(text):
            term = months
            break
    wants_warranty = term is not None or bool(re.search(r"\bwarranty\b|\bprotection plan\b", text, re.IGNORECASE))
    wants_financing = bool(
        re.search(r"\b(?:financing|finance|installment|emi|pay later|monthly payments?)\b", text, re.IGNORECASE)
    )
    resolved_budget = budget_cents
    if resolved_budget is None:
        resolved_budget = parse_budget_cents_line(prompt)
    if resolved_budget is None:
        resolved_budget = parse_budget_phrase(text)
    primary = "laptop"
    if "laptop" in categories:
        primary = "laptop"
    elif categories:
        primary = categories[0]
    accessories = [category for category in categories if category != primary]
    return Intent(
        shopper_text=text,
        budget_cents=resolved_budget,
        primary_category=primary,
        accessory_categories=accessories,
        wants_warranty=wants_warranty,
        warranty_term_months=term,
        wants_financing=wants_financing,
        prefer_cheap=bool(_CHEAP.search(text)),
        categories_explicit=explicit,
        dropped=dropped,
    )


def inherit_categories(intent: Intent, previous_categories: list[str]) -> Intent:
    """Keep the earlier package, then add or drop categories named in the follow-up."""
    merged: list[str] = []
    for category in list(previous_categories) + _mentioned(intent.shopper_text):
        if category in intent.dropped or category in merged:
            continue
        merged.append(category)
    if not merged:
        return intent
    if "laptop" in merged:
        primary = "laptop"
    elif intent.primary_category in merged:
        primary = intent.primary_category
    else:
        primary = merged[0]
    intent.primary_category = primary
    intent.accessory_categories = [category for category in merged if category != primary]
    return intent


def choose_primary(hits: list[dict], intent: Intent) -> dict | None:
    pool = [hit for hit in hits if hit["category"] == intent.primary_category and hit["stock"] > 0]
    if intent.budget_cents is not None:
        affordable = [hit for hit in pool if hit["price_cents"] <= intent.budget_cents]
        if affordable:
            pool = affordable
        else:
            return None
    if not pool:
        return None
    if intent.prefer_cheap:
        pool.sort(key=lambda hit: (hit["price_cents"], hit["sku"]))
    else:
        pool.sort(key=lambda hit: (-hit.get("score", 0), hit["price_cents"], hit["sku"]))
    return pool[0]


def dedupe_hits(groups: list[list[dict]]) -> list[dict]:
    best: dict[str, dict] = {}
    for group in groups:
        for hit in group:
            current = best.get(hit["sku"])
            if current is None or hit.get("score", 0) > current.get("score", 0):
                best[hit["sku"]] = hit
    return list(best.values())


def pick_warranty(plans: list[dict], term_months: int | None, remaining_cents: int | None) -> dict | None:
    active = [plan for plan in plans if plan.get("active")]
    if term_months is not None:
        matched = [plan for plan in active if plan["term_months"] == term_months]
        if matched:
            active = matched
    active.sort(key=lambda plan: (plan["price_cents"], plan["plan_id"]))
    for plan in active:
        if remaining_cents is None or plan["price_cents"] <= remaining_cents:
            return plan
    return None


def build_fallback(
    catalog: Catalog,
    message: str,
    budget_cents: int | None,
    today: date,
    previous_categories: list[str] | None = None,
) -> BundleProposal | None:
    """Assemble a package without the model. Returns None when nothing fits."""
    prompt = message if budget_cents is None else f"BUDGET_CENTS: {budget_cents}\nSHOPPER_MESSAGE:\n{message}"
    intent = parse_intent(prompt, budget_cents=budget_cents)
    if previous_categories:
        intent = inherit_categories(intent, previous_categories)

    groups = [[hit.as_dict() for hit in catalog.search(intent.shopper_text or intent.primary_category, limit=8)]]
    groups.append(
        [hit.as_dict() for hit in catalog.search(intent.primary_category, category=intent.primary_category, limit=6)]
    )
    for category in intent.accessory_categories:
        groups.append([hit.as_dict() for hit in catalog.search(category, category=category, limit=4)])
    hits = dedupe_hits(groups)
    primary = choose_primary(hits, intent)
    if primary is None:
        return None

    spent = primary["price_cents"]
    accessories: list[dict] = []
    primary_product = catalog.get(primary["sku"])
    if primary_product is None:
        return None
    for category in intent.accessory_categories:
        candidates = [hit for hit in hits if hit["category"] == category and hit["stock"] > 0]
        if intent.prefer_cheap:
            candidates.sort(key=lambda hit: (hit["price_cents"], hit["sku"]))
        else:
            candidates.sort(key=lambda hit: (-hit.get("score", 0), hit["price_cents"], hit["sku"]))
        for candidate in candidates:
            product = catalog.get(candidate["sku"])
            if product is None:
                continue
            ok, _reason = check_products(primary_product, product)
            if not ok:
                continue
            if intent.budget_cents is not None and spent + candidate["price_cents"] > intent.budget_cents:
                continue
            accessories.append(candidate)
            spent += candidate["price_cents"]
            break

    warranty = None
    if intent.wants_warranty:
        remaining = None if intent.budget_cents is None else intent.budget_cents - spent
        plans = [plan_dict(plan) for plan in plans_for(primary_product)]
        warranty = pick_warranty(plans, intent.warranty_term_months, remaining)
        if warranty is not None:
            spent += warranty["price_cents"]

    if intent.budget_cents is not None and spent > intent.budget_cents:
        return None

    offer_id = None
    if intent.wants_financing:
        offer = best_eligible(spent, today)
        if offer is not None:
            offer_id = offer.offer_id

    lines = [BundleLineIn(sku=primary["sku"], quantity=1, role="primary")]
    lines.extend(BundleLineIn(sku=item["sku"], quantity=1, role="accessory") for item in accessories)
    if warranty is not None:
        lines.append(BundleLineIn(sku=warranty["plan_id"], quantity=1, role="warranty"))

    names = [primary["name"]] + [item["name"] for item in accessories]
    if warranty is not None:
        names.append(warranty["name"])
    title = f"{primary['name']} package"
    summary = "Includes " + ", ".join(names) + "."
    rationale = (
        "Deterministic fallback. Items were filtered for stock, compatibility, warranty fit, and budget. "
        "The same checks run again before this package is shown."
    )
    return BundleProposal(
        title=title,
        summary=summary,
        rationale=rationale,
        lines=lines,
        financing_offer_id=offer_id,
    )

