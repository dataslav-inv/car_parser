from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from parser.http_client import fetch_html, polite_sleep, to_float, to_int
from parser.models import Listing, SearchQuery

BASE = "https://auto.ria.com"

BRAND_SLUGS = {
    "шкода": "skoda",
    "skoda": "skoda",
    "фольксваген": "volkswagen",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "бмв": "bmw",
    "bmw": "bmw",
    "ауди": "audi",
    "audi": "audi",
    "тойота": "toyota",
    "toyota": "toyota",
    "мерседес": "mercedes-benz",
    "mercedes": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "форд": "ford",
    "ford": "ford",
    "опель": "opel",
    "opel": "opel",
    "рено": "renault",
    "renault": "renault",
    "хюндай": "hyundai",
    "hyundai": "hyundai",
    "кіа": "kia",
    "kia": "kia",
    "nissan": "nissan",
    "ніссан": "nissan",
    "mazda": "mazda",
    "мазда": "mazda",
    "honda": "honda",
    "хонда": "honda",
    "peugeot": "peugeot",
    "пежо": "peugeot",
    "citroen": "citroen",
    "ситроен": "citroen",
    "volvo": "volvo",
    "вольво": "volvo",
    "lexus": "lexus",
    "лексус": "lexus",
}


def search(query: SearchQuery) -> list[Listing]:
    found: list[Listing] = []
    seen: set[str] = set()
    for page in range(query.pages):
        url = query.url or _search_url(query, page + 1)
        html = fetch_html(url)
        batch = parse_html(html)
        for item in batch:
            if item.external_id in seen:
                continue
            seen.add(item.external_id)
            if query.matches(item):
                found.append(item)
        if page + 1 < query.pages:
            polite_sleep(query.delay)
    return found


def parse_html(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a.product-card")
    listings: list[Listing] = []
    for card in cards:
        href = card.get("href") or ""
        if "/auto_" not in href:
            continue
        external_id = card.get("data-car-id") or card.get("id") or _id_from_href(href)
        if not external_id:
            continue
        text = card.get_text("\n", strip=True)
        title = _title(card, text)
        brand, model = _brand_model(href, title)
        image = card.select_one("img")
        photo = ""
        region = ""
        if image:
            photo = image.get("src") or image.get("data-src") or ""
            region = _region_from_alt(image.get("alt") or image.get("title") or "")
        price_usd, price_uah = _prices(text)
        listings.append(
            Listing(
                source="autoria",
                external_id=str(external_id),
                url=href if href.startswith("http") else BASE + href,
                title=title,
                brand=brand,
                model=model,
                year=_year(title),
                price_usd=price_usd,
                price_uah=price_uah,
                mileage_km=_mileage(text),
                fuel=_fuel(text),
                gearbox=_gearbox(text),
                engine_l=_engine(text),
                region=region,
                seller_type="dealer" if "дилер" in text.lower() else "private",
                photo=photo,
                published_hint=_published(text),
            )
        )
    return listings


def _search_url(query: SearchQuery, page: int) -> str:
    brand = BRAND_SLUGS.get(query.brand.lower(), _slug(query.brand)) if query.brand else ""
    model = _slug(query.model) if query.model else ""
    if brand and model:
        path = f"{BASE}/uk/car/{brand}/{model}/"
    elif brand:
        path = f"{BASE}/uk/car/{brand}/"
    else:
        path = f"{BASE}/uk/search/"
    # У каталога марки page начинается с 1. Параметр size на этом пути даёт 404.
    return path + "?" + urlencode({"page": page})


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _id_from_href(href: str) -> str:
    match = re.search(r"_(\d+)\.html", href)
    return match.group(1) if match else ""


def _title(card, text: str) -> str:
    heading = card.select_one(".common-text.titleS, .common-text.titleM, h3, h2")
    if heading:
        return heading.get_text(" ", strip=True)
    for line in text.split("\n"):
        if re.search(r"\b20\d{2}\b|\b19\d{2}\b", line) and len(line) < 80:
            return line
    return text.split("\n")[0][:120]


def _brand_model(href: str, title: str) -> tuple[str, str]:
    match = re.search(r"/auto_([a-z0-9]+)_([a-z0-9-]+)_\d+\.html", href)
    if match:
        return match.group(1).capitalize(), match.group(2).replace("-", " ").title()
    parts = title.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def _year(title: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", title)
    return int(match.group(0)) if match else None


def _prices(text: str) -> tuple[float | None, float | None]:
    pair = re.findall(r"([\d\s\u00a0\u202f]+)\s*\$\s*·\s*([\d\s\u00a0\u202f]+)\s*грн", text)
    if pair:
        usd, uah = pair[-1]
        return to_float(usd), to_float(uah)
    usd_only = re.findall(r"([\d\s\u00a0\u202f]+)\s*\$", text)
    return (to_float(usd_only[-1]) if usd_only else None), None


def _mileage(text: str) -> int | None:
    thousands = re.search(r"([\d\s\u00a0\u202f]+)\s*тис\.?\s*км", text, re.I)
    if thousands:
        value = to_float(thousands.group(1))
        return int(value * 1000) if value is not None else None
    exact = re.search(r"([\d\s\u00a0\u202f]+)\s*км", text, re.I)
    return to_int(exact.group(1)) if exact else None


def _fuel(text: str) -> str:
    low = text.lower()
    for name in ("електро", "гібрид", "гибрид", "дизель", "дизель", "газ/бензин", "газ", "бензин"):
        if name in low:
            return name
    return ""


def _gearbox(text: str) -> str:
    low = text.lower()
    if "автомат" in low or "tiptronic" in low or "steptronic" in low or "dsg" in low:
        return "automatic"
    if "механі" in low or "механ" in low or "ручна" in low:
        return "manual"
    if "робот" in low:
        return "robot"
    if "варіатор" in low or "вариатор" in low:
        return "cvt"
    return ""


def _engine(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*л", text)
    return to_float(match.group(1)) if match else None


def _region_from_alt(alt: str) -> str:
    match = re.search(r"\sв\s+(.+)$", alt)
    return match.group(1).strip() if match else ""


def _published(text: str) -> str:
    match = re.search(r"(\d+\s+(?:хвилин|годин|днів|день|тижн)\w*\s+тому|сьогодні|вчора)", text, re.I)
    return match.group(1) if match else ""
