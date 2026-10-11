from __future__ import annotations

import re
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup

from parser.http_client import fetch_html, polite_sleep, to_float
from parser.models import Listing, SearchQuery

BASE = "https://www.olx.ua"


def search(query: SearchQuery) -> list[Listing]:
    found: list[Listing] = []
    seen: set[str] = set()
    for page in range(1, query.pages + 1):
        url = query.url or _search_url(query, page)
        html = fetch_html(url)
        for item in parse_html(html):
            if item.external_id in seen or not query.matches(item):
                continue
            seen.add(item.external_id)
            found.append(item)
        if page < query.pages:
            polite_sleep(query.delay)
    return found


def parse_html(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("[data-cy='l-card'], div[data-testid='l-card']")
    if not cards:
        cards = [
            anchor.find_parent("div") or anchor
            for anchor in soup.select("a[href*='/obyavlenie/'], a[href*='/d/uk/']")
        ]
    listings: list[Listing] = []
    for card in cards:
        anchor = card if getattr(card, "name", "") == "a" else card.select_one("a[href]")
        if not anchor:
            continue
        href = anchor.get("href") or ""
        external_id = _id_from_href(href)
        if not external_id:
            continue
        text = card.get_text("\n", strip=True)
        title = anchor.get_text(" ", strip=True) or text.split("\n")[0]
        price_usd, price_uah = _prices(text)
        listings.append(
            Listing(
                source="olx",
                external_id=external_id,
                url=href if href.startswith("http") else BASE + href,
                title=title[:160],
                brand=_first_word(title),
                model=_second_word(title),
                year=_year(text),
                price_usd=price_usd,
                price_uah=price_uah,
                mileage_km=_mileage(text),
                fuel=_fuel(text),
                gearbox=_gearbox(text),
                region=_region(text),
                seller_type="private",
            )
        )
    return _unique(listings)


def _search_url(query: SearchQuery, page: int) -> str:
    words = " ".join(part for part in (query.brand, query.model) if part)
    path = "/uk/transport/legkovye-avtomobili/"
    if words:
        path += "q-" + quote(words) + "/"
    params = {"search[order]": "created_at:desc", "page": page}
    if query.price_from:
        params["search[filter_float_price:from]"] = int(query.price_from)
    if query.price_to:
        params["search[filter_float_price:to]"] = int(query.price_to)
    return BASE + path + "?" + urlencode(params)


def _id_from_href(href: str) -> str:
    match = re.search(r"-ID([A-Za-z0-9]+)\.html", href) or re.search(r"/(\d{6,})(?:\.html)?", href)
    return match.group(1) if match else ""


def _prices(text: str) -> tuple[float | None, float | None]:
    usd = re.search(r"([\d\s\u00a0]+)\s*\$", text)
    uah = re.search(r"([\d\s\u00a0.,]+)\s*грн", text, re.I)
    usd_value = to_float(usd.group(1)) if usd else None
    uah_value = to_float(uah.group(1)) if uah else None
    return usd_value, uah_value


def _mileage(text: str) -> int | None:
    match = re.search(r"([\d\s\u00a0]+)\s*тис\.?\s*км", text, re.I)
    if not match:
        return None
    value = to_float(match.group(1))
    return int(value * 1000) if value is not None else None


def _year(text: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else None


def _fuel(text: str) -> str:
    low = text.lower()
    for name in ("дизель", "бензин", "газ", "електро", "гібрид"):
        if name in low:
            return name
    return ""


def _gearbox(text: str) -> str:
    low = text.lower()
    if "автомат" in low:
        return "automatic"
    if "механ" in low:
        return "manual"
    return ""


def _region(text: str) -> str:
    match = re.search(r"([А-ЯІЇЄҐ][^-\n]{2,40})\s+-\s+(?:Сьогодні|Вчора|\d)", text)
    return match.group(1).strip() if match else ""


def _first_word(title: str) -> str:
    parts = title.split()
    return parts[0] if parts else ""


def _second_word(title: str) -> str:
    parts = title.split()
    return parts[1] if len(parts) > 1 else ""


def _unique(items: list[Listing]) -> list[Listing]:
    seen: set[str] = set()
    unique: list[Listing] = []
    for item in items:
        if item.external_id in seen:
            continue
        seen.add(item.external_id)
        unique.append(item)
    return unique
