"""Telegram auth, metadata sanitising, rate limiting."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from collections import deque
from urllib.parse import parse_qsl

ALLOWED_META = {
    "capturedAt", "cameraFacing", "imageWidth", "imageHeight", "imageType", "imageSize",
    "screenWidth", "screenHeight", "viewportWidth", "viewportHeight", "pixelRatio",
    "language", "languages", "timezone", "platform", "userAgent",
    "hardwareConcurrency", "deviceMemory", "batteryLevel", "batteryCharging",
}
MINIMAL_META = {
    "capturedAt", "cameraFacing", "imageWidth", "imageHeight", "imageType", "imageSize",
}


class AuthError(Exception):
    pass


class MetaError(ValueError):
    pass


def verify_init_data(raw: str, bot_token: str, max_age: int = 3600, now: float | None = None) -> dict:
    """Validate Telegram WebApp initData (HMAC) and return the user."""
    if not raw or len(raw) > 10000:
        raise AuthError("Missing Telegram session")
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise AuthError("Missing Telegram signature")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("Invalid Telegram signature")
    try:
        age = (now if now is not None else time.time()) - int(pairs["auth_date"])
        user = json.loads(pairs["user"])
        uid = int(user["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise AuthError("Invalid Telegram user")
    if age > max_age or age < -60:
        raise AuthError("Session expired")
    return {
        "id": uid,
        "username": user.get("username"),
        "first_name": user.get("first_name", ""),
        "language_code": user.get("language_code"),
    }


def safe_meta(raw: str) -> dict:
    """Whitelist + type-check client metadata."""
    if len(raw or "") > 8000:
        raise MetaError("Metadata too large")
    try:
        obj = json.loads(raw or "{}")
    except json.JSONDecodeError:
        raise MetaError("Invalid metadata")
    if not isinstance(obj, dict):
        raise MetaError("Metadata must be an object")
    clean: dict = {}
    for k, v in obj.items():
        if k not in ALLOWED_META:
            continue
        if k == "languages":
            if isinstance(v, list):
                clean[k] = [str(x)[:40] for x in v[:5]]
        elif v is None or isinstance(v, bool):
            clean[k] = v
        elif isinstance(v, (int, float)):
            if math.isfinite(v):
                clean[k] = v
        elif isinstance(v, str):
            clean[k] = v[:300]
    return clean


class RateLimiter:
    """Small in-memory sliding-window limiter."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict = {}

    def allow(self, key, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self._hits) > 5000:  # opportunistic cleanup
            for k in [k for k, d in self._hits.items() if not d or now - d[-1] > self.window]:
                self._hits.pop(k, None)
        return True
