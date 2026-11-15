"""FastAPI: Mini App host + capture endpoint."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import BufferedInputFile
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .i18n import t
from .imaging import ImageError, process_image
from .report import build_report
from .security import MINIMAL_META, AuthError, MetaError, RateLimiter, safe_meta, verify_init_data

log = logging.getLogger("w8.api")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
CSP = ("default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; "
       "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'self' https://*.telegram.org")
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}


def create_api(s, db, bot, limiter: RateLimiter | None = None) -> FastAPI:
    api = FastAPI(title="W8Tracker", docs_url=None, redoc_url=None, openapi_url=None)
    limiter = limiter or RateLimiter(s.minute_limit, 60)
    web_dir = Path(__file__).resolve().parent.parent / "web"

    @api.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.update(HEADERS)
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def auth(x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data")):
        try:
            return verify_init_data(x_telegram_init_data, s.bot_token, s.auth_max_age)
        except AuthError as e:
            raise HTTPException(401, str(e))

    @api.get("/")
    async def home():
        return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})

    @api.get("/healthz")
    async def healthz():
        ok = await db.ping()
        return JSONResponse({"ok": ok}, status_code=200 if ok else 503)

    @api.get("/api/config")
    async def config(user: dict = Depends(auth)):
        rec = await db.upsert_user(user["id"], user["username"], user["first_name"], user["language_code"])
        used = await db.today_count(user["id"])
        return {"lang": rec["lang"], "detailed": rec["detailed"],
                "remaining": max(0, s.daily_limit - used), "maxSide": s.max_side}

    @api.post("/api/capture")
    async def capture(request: Request, photo: UploadFile = File(...), metadata: str = Form("{}"),
                      user: dict = Depends(auth)):
        uid = user["id"]
        rec = await db.upsert_user(uid, user["username"], user["first_name"], user["language_code"])
        lang = rec["lang"]
        if not limiter.allow(uid):
            raise HTTPException(429, t(lang, "err_rate"))
        used = await db.today_count(uid)
        if used >= s.daily_limit:
            raise HTTPException(429, t(lang, "err_daily", n=s.daily_limit))
        cl = request.headers.get("content-length", "")
        if cl.isdigit() and int(cl) > s.max_bytes + 200_000:
            raise HTTPException(413, t(lang, "err_size", mb=s.max_bytes // 1048576))
        if photo.content_type not in ALLOWED_TYPES:
            raise HTTPException(415, t(lang, "err_type"))
        data = await photo.read(s.max_bytes + 1)
        if not data or len(data) > s.max_bytes:
            raise HTTPException(413, t(lang, "err_size", mb=s.max_bytes // 1048576))
        try:
            meta = safe_meta(metadata)
        except MetaError:
            raise HTTPException(400, t(lang, "err_meta"))
        try:
            jpeg, (w, h), _orig = await asyncio.to_thread(process_image, data, s.max_side)
        except ImageError:
            raise HTTPException(400, t(lang, "err_image"))

        detailed = bool(rec["detailed"]) and len(meta) > len(MINIMAL_META & meta.keys())
        if not rec["detailed"]:
            meta = {k: v for k, v in meta.items() if k in MINIMAL_META}
        meta.update(imageWidth=w, imageHeight=h, imageType="image/jpeg", imageSize=len(jpeg))

        try:
            sent = await bot.send_photo(uid, BufferedInputFile(jpeg, filename="capture.jpg"),
                                        caption=t(lang, "photo_caption"))
            rep = await bot.send_message(uid, build_report(meta, w, h, len(jpeg), "image/jpeg", lang, detailed))
        except TelegramForbiddenError:
            raise HTTPException(403, t(lang, "err_start"))
        except TelegramAPIError:
            log.exception("Telegram delivery failed")
            raise HTTPException(502, t(lang, "err_send"))
        cid = await db.add_capture(uid, sent.photo[-1].file_id, "image/jpeg", len(jpeg), meta,
                                   sent.message_id, rep.message_id)
        return {"ok": True, "id": cid, "remaining": max(0, s.daily_limit - used - 1)}

    api.mount("/static", StaticFiles(directory=web_dir), name="static")
    return api
