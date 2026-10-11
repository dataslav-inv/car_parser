from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)

DEFAULT_DB_PATH = ROOT_DIR / "data" / "listings.sqlite"


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or default


def get_int_env(name: str, default: int) -> int:
    value = get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_float_env(name: str, default: float) -> float:
    value = get_env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_db_path() -> Path:
    value = get_env("CAR_PARSER_DB_PATH")
    if value is None:
        return DEFAULT_DB_PATH
    return Path(value).expanduser()
