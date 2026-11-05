"""Synthetic electronics catalog.

Prices and stock are made up. Vendors (Northstar, Pixelwell, Harbor) are
fictional. Nothing here is a quote from a real retailer.
"""

from dataclasses import dataclass, field


@dataclass
class Product:
    sku: str
    name: str
    vendor: str
    category: str
    series: str
    price_cents: int
    stock: int
    description: str
    ports: frozenset[str] = field(default_factory=frozenset)
    requires_port: str | None = None
    universal: bool = False

    def index_text(self) -> str:
        ports = " ".join(sorted(self.ports)) or "none"
        requires = self.requires_port or "none"
        return (
            f"{self.name}. category {self.category}. vendor {self.vendor}. "
            f"series {self.series}. ports {ports}. requires {requires}. {self.description}"
        )


def _product(
    sku: str,
    name: str,
    vendor: str,
    category: str,
    series: str,
    price_cents: int,
    stock: int,
    description: str,
    ports: str = "",
    requires_port: str | None = None,
    universal: bool = False,
) -> Product:
    return Product(
        sku=sku,
        name=name,
        vendor=vendor,
        category=category,
        series=series,
        price_cents=price_cents,
        stock=stock,
        description=description,
        ports=frozenset(part for part in ports.split() if part),
        requires_port=requires_port,
        universal=universal,
    )


PRODUCTS: tuple[Product, ...] = (
    _product(
        "NS-PRO-16",
        "Northstar Pro 16",
        "Northstar",
        "laptop",
        "ns-pro",
        189_900,
        12,
        "16-inch laptop for video editing, color grading, and long timelines. "
        "USB4, HDMI, and USB-C. Built for creator work.",
        ports="usb4 usbc hdmi",
    ),
    _product(
        "NS-AIR-14",
        "Northstar Air 14",
        "Northstar",
        "laptop",
        "ns-air",
        129_900,
        8,
        "Thin 14-inch laptop for travel and everyday writing. USB-C only, no HDMI and no USB4.",
        ports="usbc",
    ),
    _product(
        "PW-SLIM-14",
        "Pixelwell Slim 14",
        "Pixelwell",
        "laptop",
        "pw-slim",
        99_900,
        20,
        "Lightweight 14-inch student laptop for class notes, campus carry, and web work. USB-C only.",
        ports="usbc",
    ),
    _product(
        "HB-STUDIO-16",
        "Harbor Studio 16",
        "Harbor",
        "laptop",
        "hb-studio",
        159_900,
        6,
        "16-inch creator laptop for video editing, photo work, and an external monitor. "
        "USB4, HDMI, and USB-C.",
        ports="usb4 usbc hdmi",
    ),
    _product(
        "PW-VECTOR-17",
        "Pixelwell Vector 17",
        "Pixelwell",
        "laptop",
        "pw-vector",
        219_900,
        4,
        "17-inch gaming laptop with a fast display for high-refresh games. USB4, HDMI, and USB-C.",
        ports="usb4 usbc hdmi",
    ),
    _product(
        "NS-REFURB-14",
        "Northstar Air 14 Refurbished",
        "Northstar",
        "laptop",
        "ns-air",
        74_900,
        0,
        "Refurbished travel laptop. Currently out of stock. USB-C only.",
        ports="usbc",
    ),
    _product(
        "NS-DOCK-TB",
        "Northstar USB4 Dock",
        "Northstar",
        "dock",
        "dock-tb",
        24_900,
        15,
        "Desktop USB4 dock for a laptop that has a USB4 port. Adds HDMI, ethernet, and extra ports.",
        requires_port="usb4",
    ),
    _product(
        "PW-DOCK-C",
        "Pixelwell USB-C Dock",
        "Pixelwell",
        "dock",
        "dock-c",
        12_900,
        30,
        "Compact USB-C dock with HDMI output for laptops that only have USB-C.",
        requires_port="usbc",
    ),
    _product(
        "HB-DOCK-A",
        "Harbor USB-A Mini Dock",
        "Harbor",
        "dock",
        "dock-a",
        4_900,
        40,
        "Older mini dock that needs a USB-A port on the laptop. "
        "Current laptops in this catalog do not have USB-A.",
        requires_port="usb-a",
    ),
    _product(
        "NS-MON-27",
        "Northstar 27 Monitor",
        "Northstar",
        "monitor",
        "mon-27",
        32_900,
        10,
        "27-inch monitor for documents and video editing. Includes HDMI and USB-C cables.",
        universal=True,
    ),
    _product(
        "HB-MON-32",
        "Harbor 32 Monitor",
        "Harbor",
        "monitor",
        "mon-32",
        54_900,
        4,
        "32-inch color monitor for photo work and a wide desktop. Includes HDMI and USB-C cables.",
        universal=True,
    ),
    _product(
        "NS-KEY-MECH",
        "Northstar Mechanical Keyboard",
        "Northstar",
        "keyboard",
        "key",
        12_900,
        25,
        "Full-size mechanical keyboard. Works with any laptop.",
        universal=True,
    ),
    _product(
        "NS-KEY-SLIM",
        "Northstar Slim Keyboard",
        "Northstar",
        "keyboard",
        "key",
        7_900,
        22,
        "Low-profile keyboard for a small desk. Works with any laptop.",
        universal=True,
    ),
    _product(
        "PW-MOUSE",
        "Pixelwell Silent Mouse",
        "Pixelwell",
        "mouse",
        "mouse",
        3_900,
        50,
        "Quiet wireless mouse for class and an office. Works with any laptop.",
        universal=True,
    ),
    _product(
        "HB-HEAD-1",
        "Harbor Studio Headset",
        "Harbor",
        "headset",
        "audio",
        8_900,
        18,
        "Closed headset for calls and video editing playback. Works with any laptop.",
        universal=True,
    ),
    _product(
        "PW-HEAD-2",
        "Pixelwell Campus Headphones",
        "Pixelwell",
        "headset",
        "audio",
        4_900,
        28,
        "Light headphones for a student commute. Works with any laptop.",
        universal=True,
    ),
)
