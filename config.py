"""Environment-based settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    webapp_url: str
    admin_ids: frozenset = frozenset()
    port: int = 8000
    retention_days: int = 30      # DB records older than this are purged (0 = keep)
    daily_limit: int = 20         # max submissions per user per rolling 24h
    minute_limit: int = 6         # max API submissions per user per minute
    max_bytes: int = 8 * 1024 * 1024
    max_side: int = 2048          # longest image side after server re-encode
    auth_max_age: int = 3600      # Telegram initData validity (seconds)
    log_level: str = "INFO"


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    webapp = _required("WEBAPP_URL").rstrip("/")
    if not webapp.startswith("https://"):
        raise RuntimeError("WEBAPP_URL must be an https:// URL (Telegram requirement)")
    admins = frozenset(
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
    )
    return Settings(
        bot_token=_required("BOT_TOKEN"),
        database_url=_required("DATABASE_URL"),
        webapp_url=webapp,
        admin_ids=admins,
        port=_int("PORT", 8000),
        retention_days=_int("RETENTION_DAYS", 30),
        daily_limit=_int("DAILY_LIMIT", 20),
        minute_limit=_int("MINUTE_LIMIT", 6),
        max_bytes=_int("MAX_UPLOAD_MB", 8) * 1024 * 1024,
        max_side=_int("MAX_IMAGE_SIDE", 2048),
        auth_max_age=_int("AUTH_MAX_AGE", 3600),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
