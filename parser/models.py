from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Listing:
    source: str
    external_id: str
    url: str
    title: str
    brand: str = ""
    model: str = ""
    year: int | None = None
    price_usd: float | None = None
    price_uah: float | None = None
    mileage_km: int | None = None
    fuel: str = ""
    gearbox: str = ""
    engine_l: float | None = None
    region: str = ""
    seller_type: str = ""
    photo: str = ""
    published_hint: str = ""

    def key(self) -> tuple[str, str]:
        return self.source, self.external_id

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


ALIASES = {
    "шкода": "skoda",
    "октавия": "octavia",
    "фольксваген": "volkswagen",
    "пассат": "passat",
    "бмв": "bmw",
    "ауди": "audi",
    "тойота": "toyota",
    "мерседес": "mercedes",
    "форд": "ford",
    "опель": "opel",
    "рено": "renault",
    "хюндай": "hyundai",
    "кіа": "kia",
    "киа": "kia",
    "ніссан": "nissan",
    "ниссан": "nissan",
    "мазда": "mazda",
    "хонда": "honda",
    "пежо": "peugeot",
    "ситроен": "citroen",
    "вольво": "volvo",
    "лексус": "lexus",
}


def _variants(value: str) -> list[str]:
    text = value.lower().strip()
    if not text:
        return []
    alias = ALIASES.get(text, "")
    return [item for item in (text, alias) if item]


@dataclass
class SearchQuery:
    brand: str = ""
    model: str = ""
    year_from: int | None = None
    year_to: int | None = None
    price_from: float | None = None
    price_to: float | None = None
    mileage_to: int | None = None
    region: str = ""
    pages: int = 1
    page_size: int = 20
    url: str = ""
    delay: float = 2.0

    def matches(self, item: Listing) -> bool:
        haystack = f"{item.brand} {item.model} {item.title}".lower()
        if self.brand and not any(part in haystack for part in _variants(self.brand)):
            return False
        if self.model and not any(part in haystack for part in _variants(self.model)):
            return False
        if self.year_from and (item.year or 0) < self.year_from:
            return False
        if self.year_to and (item.year or 9999) > self.year_to:
            return False
        if self.price_from is not None and (item.price_usd or 0) < self.price_from:
            return False
        if self.price_to is not None and (item.price_usd is None or item.price_usd > self.price_to):
            return False
        if self.mileage_to is not None and (item.mileage_km is None or item.mileage_km > self.mileage_to):
            return False
        if self.region and self.region.lower() not in (item.region or "").lower():
            return False
        return True


@dataclass
class FetchResult:
    source: str
    listings: list[Listing] = field(default_factory=list)
    warning: str = ""
