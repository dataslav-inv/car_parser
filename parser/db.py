from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from parser.models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    year INTEGER,
    price_usd REAL,
    price_uah REAL,
    mileage_km INTEGER,
    fuel TEXT,
    gearbox TEXT,
    engine_l REAL,
    region TEXT,
    seller_type TEXT,
    photo TEXT,
    published_hint TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS price_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    price_usd REAL,
    price_uah REAL
);

CREATE INDEX IF NOT EXISTS idx_listings_brand ON listings(brand, model, year);
CREATE INDEX IF NOT EXISTS idx_events_listing ON price_events(source, external_id, seen_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def upsert(self, item: Listing) -> str:
        now = utcnow()
        existing = self.conn.execute(
            "SELECT price_usd, price_uah, first_seen_at FROM listings WHERE source=? AND external_id=?",
            (item.source, item.external_id),
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO listings (
                    source, external_id, url, title, brand, model, year,
                    price_usd, price_uah, mileage_km, fuel, gearbox, engine_l,
                    region, seller_type, photo, published_hint, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.source, item.external_id, item.url, item.title, item.brand, item.model,
                    item.year, item.price_usd, item.price_uah, item.mileage_km, item.fuel,
                    item.gearbox, item.engine_l, item.region, item.seller_type, item.photo,
                    item.published_hint, now, now,
                ),
            )
            self._add_event(item, now)
            self.conn.commit()
            return "new"
        self.conn.execute(
            """
            UPDATE listings SET
                url=?, title=?, brand=?, model=?, year=?, price_usd=?, price_uah=?,
                mileage_km=?, fuel=?, gearbox=?, engine_l=?, region=?, seller_type=?,
                photo=?, published_hint=?, last_seen_at=?, status='active'
            WHERE source=? AND external_id=?
            """,
            (
                item.url, item.title, item.brand, item.model, item.year, item.price_usd,
                item.price_uah, item.mileage_km, item.fuel, item.gearbox, item.engine_l,
                item.region, item.seller_type, item.photo, item.published_hint, now,
                item.source, item.external_id,
            ),
        )
        changed = existing["price_usd"] != item.price_usd or existing["price_uah"] != item.price_uah
        if changed:
            self._add_event(item, now)
        self.conn.commit()
        return "price_changed" if changed else "seen"

    def _add_event(self, item: Listing, seen_at: str) -> None:
        self.conn.execute(
            "INSERT INTO price_events (source, external_id, seen_at, price_usd, price_uah) VALUES (?, ?, ?, ?, ?)",
            (item.source, item.external_id, seen_at, item.price_usd, item.price_uah),
        )

    def query(
        self,
        brand: str = "",
        model: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        price_to: float | None = None,
        source: str = "",
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        clauses = ["status='active'"]
        params: list[object] = []
        if brand:
            clauses.append("brand LIKE ?")
            params.append(f"%{brand}%")
        if model:
            clauses.append("model LIKE ?")
            params.append(f"%{model}%")
        if year_from:
            clauses.append("year >= ?")
            params.append(year_from)
        if year_to:
            clauses.append("year <= ?")
            params.append(year_to)
        if price_to is not None:
            clauses.append("price_usd <= ?")
            params.append(price_to)
        if source:
            clauses.append("source = ?")
            params.append(source)
        params.append(limit)
        sql = f"""
            SELECT * FROM listings
            WHERE {' AND '.join(clauses)}
            ORDER BY last_seen_at DESC
            LIMIT ?
        """
        return list(self.conn.execute(sql, params))

    def stats(self, brand: str = "", model: str = "", year_from: int | None = None, year_to: int | None = None) -> dict:
        clauses = ["l.price_usd IS NOT NULL"]
        params: list[object] = []
        if brand:
            clauses.append("l.brand LIKE ?")
            params.append(f"%{brand}%")
        if model:
            clauses.append("l.model LIKE ?")
            params.append(f"%{model}%")
        if year_from:
            clauses.append("l.year >= ?")
            params.append(year_from)
        if year_to:
            clauses.append("l.year <= ?")
            params.append(year_to)
        where = " AND ".join(clauses)
        rows = list(self.conn.execute(f"SELECT l.price_usd, l.mileage_km, l.year, l.source FROM listings l WHERE {where}", params))
        prices = sorted(row["price_usd"] for row in rows)
        by_source: dict[str, list[float]] = {}
        for row in rows:
            by_source.setdefault(row["source"], []).append(row["price_usd"])
        events = list(
            self.conn.execute(
                f"""
                SELECT substr(e.seen_at, 1, 7) AS month, e.price_usd
                FROM price_events e
                JOIN listings l ON l.source=e.source AND l.external_id=e.external_id
                WHERE {where}
                """,
                params,
            )
        )
        monthly: dict[str, list[float]] = {}
        for event in events:
            monthly.setdefault(event["month"], []).append(event["price_usd"])
        return {
            "count": len(prices),
            "median_usd": _median(prices),
            "p25_usd": _percentile(prices, 0.25),
            "p75_usd": _percentile(prices, 0.75),
            "by_source": {name: {"count": len(vals), "median_usd": _median(sorted(vals))} for name, vals in by_source.items()},
            "by_month": {month: {"count": len(vals), "median_usd": _median(sorted(vals))} for month, vals in sorted(monthly.items())},
        }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return round((values[mid - 1] + values[mid]) / 2, 2)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
    return values[index]
