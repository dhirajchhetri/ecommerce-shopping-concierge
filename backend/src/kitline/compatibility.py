"""Accessory compatibility.

Docks declare the host port they need. Keyboards, mice, headsets, and monitors
in this catalog ship with their own cables or a wireless receiver and are
treated as universal. An accessory with no matching rule fails closed.
"""

from kitline.catalog_data import Product

UNIVERSAL_CATEGORIES = frozenset({"keyboard", "mouse", "headset", "monitor"})


def check_products(primary: Product, accessory: Product) -> tuple[bool, str]:
    if accessory.sku == primary.sku:
        return False, "An item cannot be an accessory of itself."
    if accessory.category == "laptop":
        return False, "A laptop is not an accessory."
    if accessory.universal or accessory.category in UNIVERSAL_CATEGORIES:
        return True, f"{accessory.name} works with {primary.name}."
    if accessory.requires_port:
        if accessory.requires_port in primary.ports:
            return True, f"{primary.name} has a {accessory.requires_port} port, which {accessory.name} needs."
        return (
            False,
            f"{primary.name} has no {accessory.requires_port} port, and {accessory.name} requires one.",
        )
    return False, f"No compatibility rule allows {accessory.sku} with {primary.sku}."
