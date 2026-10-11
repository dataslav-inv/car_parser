from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from parser.config import get_db_path, get_float_env, get_int_env, get_env
from parser.db import Store
from parser.http_client import SourceBlocked
from parser.models import SearchQuery
from parser.sources import SOURCES

DEFAULT_DB = get_db_path()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Єдиний пошук оголошень AUTO.RIA, RST та OLX з історією цін."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Зібрати актуальні оголошення")
    _add_filters(search)
    search.add_argument("--sources", default=get_env("CAR_PARSER_SOURCES", "autoria,rst,olx"), help="autoria,rst,olx")
    search.add_argument("--pages", type=int, default=get_int_env("CAR_PARSER_PAGES", 1))
    search.add_argument("--url", default="", help="Готове посилання на вивід із фільтрами сайту")
    search.add_argument("--html", default="", help="Збережений HTML виводу, якщо сайт заблокував прямий запит")
    search.add_argument("--html-source", default="autoria", choices=sorted(SOURCES))
    search.add_argument("--db", default=str(DEFAULT_DB))
    search.add_argument("--delay", type=float, default=get_float_env("CAR_PARSER_DELAY", 2.0))
    search.add_argument("--json", action="store_true", help="Виводити JSON замість таблиці")

    show = sub.add_parser("show", help="Показати вже збережені оголошення")
    _add_filters(show)
    show.add_argument("--source", default="")
    show.add_argument("--limit", type=int, default=50)
    show.add_argument("--db", default=str(DEFAULT_DB))

    stats = sub.add_parser("stats", help="Медіана та перцентилі за накопиченою базою")
    _add_filters(stats)
    stats.add_argument("--db", default=str(DEFAULT_DB))

    export = sub.add_parser("export", help="Експортувати базу в CSV або JSONL")
    export.add_argument("--out", required=True)
    export.add_argument("--db", default=str(DEFAULT_DB))

    args = parser.parse_args(argv)
    if args.command == "search":
        return cmd_search(args)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "stats":
        return cmd_stats(args)
    if args.command == "export":
        return cmd_export(args)
    return 1


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--brand", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--price-from", type=float)
    parser.add_argument("--price-to", type=float)
    parser.add_argument("--mileage-to", type=int)
    parser.add_argument("--region", default="")


def cmd_search(args: argparse.Namespace) -> int:
    query = SearchQuery(
        brand=args.brand,
        model=args.model,
        year_from=args.year_from,
        year_to=args.year_to,
        price_from=args.price_from,
        price_to=args.price_to,
        mileage_to=args.mileage_to,
        region=args.region,
        pages=max(1, args.pages),
        url=args.url,
        delay=args.delay,
    )
    store = Store(args.db)
    collected = []
    sources = [name.strip() for name in args.sources.split(",") if name.strip()]
    if args.html:
        html = Path(args.html).read_text(encoding="utf-8", errors="ignore")
        adapter = SOURCES[args.html_source]
        items = [item for item in adapter.parse_html(html) if query.matches(item)]
        collected.extend(_save(store, items))
    else:
        for name in sources:
            adapter = SOURCES.get(name)
            if adapter is None:
                print(f"Невідоме джерело: {name}", file=sys.stderr)
                continue
            try:
                items = adapter.search(query)
            except SourceBlocked as exc:
                print(f"[{name}] {exc}", file=sys.stderr)
                continue
            except Exception as exc:  # noqa: BLE001 — показуємо помилку джерела і продовжуємо
                print(f"[{name}] помилка: {exc}", file=sys.stderr)
                continue
            print(f"[{name}] {len(items)} оголошень після фільтра", file=sys.stderr)
            collected.extend(_save(store, items))
    store.close()
    if args.json:
        print(json.dumps(collected, ensure_ascii=False, indent=2))
    else:
        _print_table(collected)
    print(f"Збережено в {args.db}: {len(collected)}", file=sys.stderr)
    return 0


def _save(store: Store, items: list) -> list[dict]:
    rows = []
    for item in items:
        status = store.upsert(item)
        row = item.to_row()
        row["change"] = status
        rows.append(row)
    return rows


def cmd_show(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = store.query(
        brand=args.brand,
        model=args.model,
        year_from=args.year_from,
        year_to=args.year_to,
        price_to=args.price_to,
        source=args.source,
        limit=args.limit,
    )
    store.close()
    _print_table([dict(row) for row in rows])
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = Store(args.db)
    report = store.stats(args.brand, args.model, args.year_from, args.year_to)
    store.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["count"] < 30:
        print(
            "Замало спостережень для сезону. Запускайте search щодня: медіана за місяцями з’явиться в by_month.",
            file=sys.stderr,
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = [dict(row) for row in store.query(limit=100000)]
    store.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".jsonl":
        out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    else:
        if not rows:
            out.write_text("", encoding="utf-8")
        else:
            with out.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
    print(f"{len(rows)} строк → {out}")
    return 0


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("Нічого не знайдено.")
        return
    print(f"{'src':8} {'year':4} {'usd':>8} {'km':>8}  title")
    for row in rows[:80]:
        print(
            f"{row.get('source',''):8} "
            f"{row.get('year') or '-':4} "
            f"{row.get('price_usd') or '-':>8} "
            f"{row.get('mileage_km') or '-':>8}  "
            f"{row.get('title','')[:52]}"
        )
        print(f"         {row.get('url','')}")


if __name__ == "__main__":
    raise SystemExit(main())
