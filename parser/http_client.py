from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

CHALLENGE_MARKERS = (
    "just a moment",
    "performing security verification",
    "cf-challenge",
    "challenge-platform",
    "human verification",
    "awswaf",
    "let's confirm you are human",
    "verify you are human",
)


class SourceBlocked(RuntimeError):
    """Платформа віддала перевірку замість виводу. Обхід не виконується."""


def fetch_html(url: str, timeout: float = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if _is_challenge(body) or exc.code in {403, 429, 503}:
            raise SourceBlocked(
                f"{url} повернув {exc.code}. Це перевірка доступу, парсер її не обходить."
            ) from exc
        raise
    html = raw.decode(charset, errors="ignore")
    if _is_challenge(html):
        raise SourceBlocked(
            f"{url} віддав сторінку перевірки замість оголошень. "
            "Відкрийте вивід у браузері та передайте збережений HTML через --html."
        )
    return html


def _is_challenge(html: str) -> bool:
    head = html[:8000].lower()
    return any(marker in head for marker in CHALLENGE_MARKERS)


def polite_sleep(seconds: float) -> None:
    time.sleep(max(seconds, 1.0))


_NBSP = re.compile(r"[\s\u00a0\u202f]+")


def to_float(value: str) -> float | None:
    cleaned = _NBSP.sub("", value).replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def to_int(value: str) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)
