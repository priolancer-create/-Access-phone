"""Telegram bot handlers (aiogram 3)."""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
from datetime import timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message, WebAppInfo)

from .i18n import t

router = Router()
PAGE = 5


def B(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def menu_kb(lang, url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_camera"), web_app=WebAppInfo(url=url))],
        [B(t(lang, "btn_history"), "h:0"), B(t(lang, "btn_settings"), "s:show")],
        [B(t(lang, "btn_privacy"), "privacy")]])


async def _rec(db, u):
    return await db.upsert_user(u.id, u.username, u.first_name, u.language_code)


async def _edit(msg: Message, text, kb=None):
    with contextlib.suppress(TelegramBadRequest):
        await msg.edit_text(text, reply_markup=kb)


async def _delete_msgs(bot: Bot, chat_id, ids):
    ids = list(ids)
    for i in range(0, len(ids), 100):
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_messages(chat_id, ids[i:i + 100])


# ---------- commands
@router.message(Command("start"))
async def start(m: Message, db, settings):
    r = await _rec(db, m.from_user)
    await m.answer(t(r["lang"], "welcome"), reply_markup=menu_kb(r["lang"], settings.webapp_url))


@router.message(Command("help"))
async def help_(m: Message, db):
    r = await _rec(db, m.from_user)
    await m.answer(t(r["lang"], "help"))


@router.message(Command("capture"))
async def capture(m: Message, db, settings):
    r = await _rec(db, m.from_user)
    await m.answer(t(r["lang"], "capture_prompt"), reply_markup=menu_kb(r["lang"], settings.webapp_url))


@router.message(Command("privacy"))
async def privacy(m: Message, db, settings):
    r = await _rec(db, m.from_user)
    await m.answer(t(r["lang"], "privacy", days=settings.retention_days))


@router.callback_query(F.data == "privacy")
async def privacy_cb(q: CallbackQuery, db, settings):
    r = await _rec(db, q.from_user)
    await q.message.answer(t(r["lang"], "privacy", days=settings.retention_days))
    await q.answer()


# ---------- history
async def render_history(db, uid, lang, page):
    total = await db.count_captures(uid)
    if not total:
        return t(lang, "no_history"), None
    pages = (total + PAGE - 1) // PAGE
    page = max(0, min(page, pages - 1))
    rows = await db.list_captures(uid, PAGE, page * PAGE)
    lines = [t(lang, "history_title", total=total)]
    kb = []
    for r in rows:
        when = r["consented_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(t(lang, "photo_item", id=r["id"], when=when) + f" · {r['byte_size'] / 1024:.0f} KB")
        kb.append([B(f"🖼 #{r['id']}", f"g:{r['id']}"), B(f"🗑 #{r['id']}", f"d:{r['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(B(t(lang, "prev"), f"h:{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(B(t(lang, "next"), f"h:{page + 1}"))
    kb.append(nav)
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(Command("history"))
async def history(m: Message, db):
    r = await _rec(db, m.from_user)
    text, kb = await render_history(db, m.from_user.id, r["lang"], 0)
    await m.answer(text, reply_markup=kb)


def _int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


@router.callback_query(F.data.startswith("h:"))
async def cb_history(q: CallbackQuery, db):
    r = await _rec(db, q.from_user)
    text, kb = await render_history(db, q.from_user.id, r["lang"], _int(q.data[2:]))
    await _edit(q.message, text, kb)
    await q.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(q: CallbackQuery):
    await q.answer()


@router.callback_query(F.data.startswith("g:"))
async def cb_get(q: CallbackQuery, db, bot: Bot):
    r = await _rec(db, q.from_user)
    row = await db.get_capture(q.from_user.id, _int(q.data[2:], -1))
    if not row:
        return await q.answer(t(r["lang"], "not_found"), show_alert=True)
    await bot.send_photo(q.from_user.id, row["telegram_file_id"], caption=f"#{row['id']}")
    await q.answer()


@router.callback_query(F.data.startswith("d:"))
async def cb_delete(q: CallbackQuery, db, bot: Bot):
    r = await _rec(db, q.from_user)
    _, cid, page = (q.data.split(":") + ["0", "0"])[:3]
    row = await db.delete_capture(q.from_user.id, _int(cid, -1))
    if not row:
        return await q.answer(t(r["lang"], "not_found"), show_alert=True)
    await _delete_msgs(bot, q.from_user.id, [m for m in (row["photo_message_id"], row["report_message_id"]) if m])
    text, kb = await render_history(db, q.from_user.id, r["lang"], _int(page))
    await _edit(q.message, text, kb)
    await q.answer(t(r["lang"], "deleted", id=cid))


# ---------- erase / export
@router.message(Command("deleteall"))
async def deleteall(m: Message, db):
    r = await _rec(db, m.from_user)
    L = r["lang"]
    await m.answer(t(L, "confirm_all"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        B(t(L, "yes_delete"), "da:yes"), B(t(L, "no"), "da:no")]]))


@router.callback_query(F.data.in_({"da:yes", "da:no"}))
async def cb_deleteall(q: CallbackQuery, db, bot: Bot):
    r = await _rec(db, q.from_user)
    L = r["lang"]
    if q.data == "da:no":
        await _edit(q.message, t(L, "cancelled"))
        return await q.answer()
    n, ids = await db.erase_user(q.from_user.id)
    await _delete_msgs(bot, q.from_user.id, ids)
    await _edit(q.message, t(L, "all_deleted", n=n))
    await q.answer()


@router.message(Command("export"))
async def export(m: Message, db):
    r = await _rec(db, m.from_user)
    rows = await db.export_user(m.from_user.id)
    payload = json.dumps({"user_id": m.from_user.id, "captures": rows}, ensure_ascii=False, indent=2)
    await m.answer_document(BufferedInputFile(payload.encode(), filename="w8tracker_export.json"),
                            caption=t(r["lang"], "export_caption"))


# ---------- settings
def render_settings(r):
    L = r["lang"]
    text = (f"{t(L, 'settings_title')}\n\n{t(L, 'lang_label')}: {'বাংলা' if L == 'bn' else 'English'}\n"
            f"{t(L, 'detail_label')}: {t(L, 'detail_full') if r['detailed'] else t(L, 'detail_min')}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B("🌐 বাংলা ⇄ English", "s:lang")],
        [B(f"📋 {t(L, 'detail_label')}", "s:detail")]])
    return text, kb


@router.message(Command("settings"))
async def settings_cmd(m: Message, db):
    text, kb = render_settings(await _rec(db, m.from_user))
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("s:"))
async def cb_settings(q: CallbackQuery, db):
    r = await _rec(db, q.from_user)
    action = q.data[2:]
    if action == "lang":
        r = await db.set_lang(q.from_user.id, "en" if r["lang"] == "bn" else "bn")
    elif action == "detail":
        r = await db.set_detailed(q.from_user.id, not r["detailed"])
    text, kb = render_settings(r)
    await _edit(q.message, text, kb)
    await q.answer()


# ---------- admin
@router.message(Command("stats"))
async def stats(m: Message, db, settings):
    r = await _rec(db, m.from_user)
    if m.from_user.id not in settings.admin_ids:
        return await m.answer(t(r["lang"], "admin_only"))
    s = await db.stats()
    await m.answer(t(r["lang"], "stats", users=s["users"], captures=s["captures"], day=s["day"],
                     week=s["week"], mb=s["bytes"] / 1048576))


async def set_commands(bot: Bot):
    en = [("capture", "Open camera"), ("history", "My submissions"), ("settings", "Language & report"),
          ("export", "Export my data"), ("deleteall", "Erase all my data"), ("privacy", "Privacy info"),
          ("help", "Help")]
    bn = [("capture", "ক্যামেরা খুলুন"), ("history", "আমার ছবির ইতিহাস"), ("settings", "ভাষা ও রিপোর্ট"),
          ("export", "ডেটা এক্সপোর্ট"), ("deleteall", "সব ডেটা মুছুন"), ("privacy", "গোপনীয়তা"),
          ("help", "সাহায্য")]
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in en])
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in bn], language_code="bn")
