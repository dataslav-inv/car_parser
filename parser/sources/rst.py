from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from parser.http_client import fetch_html, polite_sleep, to_float
from parser.models import Listing, SearchQuery

BASE = "https://rst.ua"


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
    listings: list[Listing] = []
    anchors = soup.select("a[href*='/oldcars/'], a[href*='/ukr/oldcars/']")
    for anchor in anchors:
        href = anchor.get("href") or ""
        external_id = _id_from_href(href)
        if not external_id:
            continue
        block = anchor.find_parent("div") or anchor
        text = block.get_text("\n", strip=True)
        title = anchor.get_text(" ", strip=True) or text.split("\n")[0]
        price_usd, price_uah = _prices(text)
        if price_usd is None and price_uah is None:
            continue
        listings.append(
            Listing(
                source="rst",
                external_id=external_id,
                url=href if href.startswith("http") else BASE + href,
                title=title[:160],
                brand=_first_word(title),
                model=_second_word(title),
                year=_year(title + " " + text),
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
    brand = _slug(query.brand)
    model = _slug(query.model)
    path = "/ukr/oldcars/"
    if brand:
        path += brand + "/"
    if model:
        path += model + "/"
    params = {"page": page, "sort": "date"}
    return BASE + path + "?" + urlencode(params)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _id_from_href(href: str) -> str:
    match = re.search(r"/(\d{5,})(?:\.html)?", href)
    return match.group(1) if match else ""


def _prices(text: str) -> tuple[float | None, float | None]:
    usd = re.search(r"([\d\s\u00a0]+)\s*\$", text)
    uah = re.search(r"([\d\s\u00a0]+)\s*грн", text, re.I)
    return (to_float(usd.group(1)) if usd else None), (to_float(uah.group(1)) if uah else None)


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
    lines = [line for line in text.split("\n") if line]
    return lines[-1][:80] if lines else ""


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
